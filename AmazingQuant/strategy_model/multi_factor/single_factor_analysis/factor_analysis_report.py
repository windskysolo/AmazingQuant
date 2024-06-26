# -*- coding: utf-8 -*-

# ------------------------------
# @Time    : 2023/11/28
# @Author  : gao
# @File    : factor_analysis_report.py 
# @Project : AmazingQuant 
# ------------------------------
import math
from datetime import datetime

from pyecharts.charts import Bar, Line, Page, Timeline
from pyecharts import options as opts
from pyecharts.components import Table
from pyecharts.options import ComponentTitleOpts, InitOpts

from AmazingQuant.constant import LocalDataFolderName, RightsAdjustment
from AmazingQuant.config.local_data_path import LocalDataPath
from AmazingQuant.data_center.api_data.get_kline import GetKlineData
from AmazingQuant.factor_center.save_get_factor import SaveGetFactor

from AmazingQuant.strategy_model.multi_factor.single_factor_analysis.ic_analysis import IcAnalysis
from AmazingQuant.strategy_model.multi_factor.single_factor_analysis.regression_analysis import RegressionAnalysis
from AmazingQuant.strategy_model.multi_factor.single_factor_analysis.stratification_analysis import \
    StratificationAnalysis


class FactorAnalysis(object):
    def __init__(self, factor, factor_name, path, benchmark_code='000300.SH'):
        self.factor = factor
        self.factor_name = factor_name
        self.path = path
        self.benchmark_code = benchmark_code

        self.stratification_analysis_obj = None
        self.regression_analysis_obj = None
        self.ic_analysis_obj = None

        kline_object = GetKlineData()
        market_data = kline_object.cache_all_stock_data(dividend_type=RightsAdjustment.BACKWARD.value, field=['close'])
        self.market_close_data = kline_object.get_market_data(market_data, field=['close'])

        # 指数行情，沪深300代替
        all_index_data = kline_object.cache_all_index_data()
        self.benchmark_df = kline_object.get_market_data(all_index_data, stock_code=[self.benchmark_code],
                                                         field=['close']).to_frame(name='close')

        # ic分析参数
        # corr_method = {‘pearsonr’,:皮尔逊相关系数，非排名类因子 ，‘spearmanr’:斯皮尔曼相关系数，排名类因子}
        self.corr_method = 'spearmanr'

        self.ic_decay = 20
        # 回归分析参数
        # 以流通市值平方根或者流通市值的倒数为权重做WLS（加权最小二乘法估计）,
        # wls_weight_method = {‘float_value_inverse’：流通市值的倒数, ‘float_value_square_root’：流通市值的倒数}
        self.wls_weight_method = 'float_value_inverse'
        # nlags: 因子收益率的自相关系数acf和偏自相关系数pacf，的阶数
        self.nlags = 10

        # 分层分析参数
        self.group_num = 5

    def ic_analysis(self):
        self.ic_analysis_obj = IcAnalysis(self.factor, self.factor_name, self.market_close_data, ic_decay=self.ic_decay)
        self.ic_analysis_obj.cal_ic_df(method=self.corr_method)
        self.ic_analysis_obj.cal_ic_indicator()
        self.ic_analysis_obj.save_ic_analysis_result(self.path, factor_name)
        return self.ic_analysis_obj

    def regression_analysis(self, ):
        self.regression_analysis_obj = RegressionAnalysis(self.factor, self.factor_name,
                                                          self.market_close_data, self.benchmark_df)
        self.regression_analysis_obj.cal_factor_return(method=self.wls_weight_method)
        self.regression_analysis_obj.cal_t_value_statistics()
        self.regression_analysis_obj.cal_net_analysis()
        self.regression_analysis_obj.cal_acf(nlags=self.nlags)

        self.regression_analysis_obj.save_regression_analysis_result(self.path, factor_name)
        return self.regression_analysis_obj

    def stratification_analysis(self):
        """
        group_num，分组组数
        """
        self.stratification_analysis_obj = StratificationAnalysis(self.factor,
                                                                  self.factor_name,
                                                                  group_num=self.group_num)
        self.stratification_analysis_obj.group_analysis()
        return self.stratification_analysis_obj

    def table_factor_information(self):
        """
        因子评价的概要
        """
        date_list = list(self.factor.index.astype('str'))
        indicator_dict = {}
        indicator_dict["因子名称"] = self.factor_name
        indicator_dict["开始时间"] = min(date_list)
        indicator_dict["结束时间"] = max(date_list)
        table_factor_information = Table()
        headers = ["指标"]
        rows = [["数据"]]
        for key, value in indicator_dict.items():
            headers.append(key)
            rows[0].append(value)
        table_factor_information.add(headers, rows)
        table_factor_information.set_global_opts(title_opts=ComponentTitleOpts(title='因子评价的概要'))
        return table_factor_information

    # IC分析
    def table_ic_result(self):
        """
        ic_result
        """
        table_ic_result = Table()
        indicator_dict = {'ic_mean': 'IC均值', 'ic_std': 'IC标准差', 'ic_ir': 'IC_IR比率', 'ic_ratio': 'IC>0占比',
                          'ic_abs_ratio': '|IC|>0.02占比', 'ic_skewness': '偏度', 'ic_kurtosis': '峰度',
                          'ic_positive_ratio': '正相关显著比例', 'ic_negative_ratio': '负相关显著比例',
                          'ic_change_ratio': '状态切换比例', 'ic_unchange_ratio': '同向比例'}
        headers = ["衰减周期"] + [str(i + 1) + '日' for i in range(self.ic_decay)]
        rows = []
        ic_result = self.ic_analysis_obj.ic_result.applymap(lambda x: format(x, '.4f'))
        for key, value in indicator_dict.items():
            data = [value] + list(ic_result.loc[key, :])
            rows.append(data)
        table_ic_result.add(headers, rows)
        table_ic_result.set_global_opts(title_opts=ComponentTitleOpts(title='IC分析—总览'))
        return table_ic_result

    def bar_ic(self):
        """
        IC时序图
        """
        date_list = list(self.ic_analysis_obj.ic_df.index.astype('str'))
        selected_map_dict = {str(i + 1) + '日': False for i in range(self.ic_decay) if
                             'delay_' + str(i + 1) != 'delay_1'}
        bar_ic = Bar() \
            .set_series_opts(areastyle_opts=opts.AreaStyleOpts(opacity=0.1),
                             markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=1, name="yAxis=1")])) \
            .set_global_opts(title_opts=opts.TitleOpts(title="IC分析—时序图",
                                                       subtitle="衰减周期：" + str(self.ic_decay)),  # 标题
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),  # 添加竖线信息
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                             legend_opts=opts.LegendOpts(orient='vertical',
                                                         pos_bottom='bottom',
                                                         pos_top='58px',
                                                         pos_left='right',
                                                         pos_right='right',
                                                         selected_map=selected_map_dict
                                                         ))  # 设置Y轴范围
        for i in range(self.ic_decay):
            ic_list = list(self.ic_analysis_obj.ic_df['delay_' + str(i + 1)].round(4))
            bar_ic = bar_ic \
                .add_xaxis(date_list) \
                .add_yaxis(str(i + 1) + "日", ic_list, label_opts=opts.LabelOpts(is_show=False), )

        return bar_ic

    def bar_ic_p_value(self):
        """
        IC检测时序图
        """
        date_list = list(self.ic_analysis_obj.p_value_df.index.astype('str'))
        selected_map_dict = {str(i + 1) + '日': False for i in range(self.ic_decay) if
                             'delay_' + str(i + 1) != 'delay_1'}
        bar_ic_p_value = Bar() \
            .set_series_opts(areastyle_opts=opts.AreaStyleOpts(opacity=0.1),
                             markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=1, name="yAxis=1")])) \
            .set_global_opts(title_opts=opts.TitleOpts(title="IC分析—P值时序图",
                                                       subtitle="衰减周期：" + str(self.ic_decay)),  # 标题
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),  # 添加竖线信息
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                             legend_opts=opts.LegendOpts(orient='vertical',
                                                         pos_bottom='bottom',
                                                         pos_top='58px',
                                                         pos_left='right',
                                                         pos_right='right',
                                                         selected_map=selected_map_dict
                                                         ))  # 设置Y轴范围
        for i in range(self.ic_decay):
            ic_p_value_list = list(self.ic_analysis_obj.p_value_df['delay_' + str(i + 1)].round(4))
            bar_ic_p_value = bar_ic_p_value \
                .add_xaxis(date_list) \
                .add_yaxis(str(i + 1) + "日", ic_p_value_list, label_opts=opts.LabelOpts(is_show=False), )
        return bar_ic_p_value

    # 回归分析
    def line_regression_net_value(self):
        """
        收益
        cumsum（累加因子净值）
        cumprod（累乘因子净值）
        benchmark_df（基准净值曲线）
        """
        cumsum_list = list(self.regression_analysis_obj.factor_return['cumsum'].round(4))
        cumprod_list = list(self.regression_analysis_obj.factor_return['cumprod'].round(4))
        benchmark_list = list(
            self.regression_analysis_obj.net_analysis_result['cumsum']['benchmark_df']['net_value'].round(4))
        all_list = cumsum_list + benchmark_list + cumprod_list
        date_list = list(self.regression_analysis_obj.factor_return.index.astype('str'))
        net_value_line = Line() \
            .add_xaxis(date_list) \
            .add_yaxis("累加因子净值", cumsum_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='max')])) \
            .add_yaxis("累乘因子净值", cumprod_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='max')])) \
            .add_yaxis("基准净值曲线", benchmark_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='max')])) \
            .set_series_opts(areastyle_opts=opts.AreaStyleOpts(opacity=0.1),
                             markline_opts=opts.MarkLineOpts(data=[opts.MarkLineItem(y=1, name="yAxis=1")]),
                             label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(title_opts=opts.TitleOpts(title="因子收益率—净值曲线",
                                                       subtitle="累加因子净值为：" + str(cumsum_list[-1]) + "\t" * 5 +
                                                                "累乘因子净值为：" + str(cumprod_list[-1]) + "\t" * 5 +
                                                                "基准净值为：" + str(benchmark_list[-1])),  # 标题
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),  # 添加竖线信息
                             yaxis_opts=opts.AxisOpts(min_=math.ceil(min(all_list) * 90) / 100,
                                                      max_=int(max(all_list) * 110) / 100),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100), )  # 设置Y轴范围

        bar_daily = Bar().add_xaxis(date_list) \
            .add_yaxis("因子日收益率（%）",
                       list((self.regression_analysis_obj.factor_return['daily'] * 100).round(4)),
                       yaxis_index=1)
        bar_daily.overlap(net_value_line)
        return net_value_line

    def bar_regression_t_value(self):
        """
        't_value_mean': 绝对值均值,
        't_value_greater_two': 绝对值序列大于2的占比
        't_value': 时序数据
        """
        t_value_statistics_dict = self.regression_analysis_obj.factor_t_value_statistics.round(4).to_dict()
        date_list = list(self.regression_analysis_obj.factor_t_value.index.astype('str'))
        t_value_list = list(self.regression_analysis_obj.factor_t_value.round(4))
        bar_t_value = Bar() \
            .add_xaxis(date_list) \
            .add_yaxis("t值", t_value_list) \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-15)),
                             yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(formatter="{value}")),
                             title_opts=opts.TitleOpts(title="因子收益率—t值时序图",
                                                       subtitle="t值的绝对值均值为：" +
                                                                str(t_value_statistics_dict[
                                                                        't_value_mean']) + "\t" * 5 +
                                                                "t值的绝对值序列大于2的占比为：" +
                                                                str(t_value_statistics_dict['t_value_greater_two'])),
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100), )
        return bar_t_value

    def table_regression_net_value(self):
        """
        收益
        cumsum（累加因子净值）
        'net_year_yield'
        'net_day_win_ratio'
        'net_day_ratio_average'
        'net_month_ratio_average'

        cumprod（累乘因子净值）
        'net_year_yield'
        'net_day_win_ratio'
        'net_day_ratio_average'
        'net_month_ratio_average'

        benchmark（基准）
        'benchmark_year_yield'
        'benchmark_day_win_ratio'
        'benchmark_day_ratio_average'
        'benchmark_month_ratio_average'
        """
        indicator_dict = {'net_year_yield': "年化收益率（%）",
                          'net_day_win_ratio': "日胜率（%）",
                          'net_day_ratio_average': "日平均收益率（%）",
                          'net_month_ratio_average': "月平均收益率（%）", }
        benchmark_indicator_list = ['benchmark_year_yield',
                                    'benchmark_day_win_ratio',
                                    'benchmark_day_ratio_average',
                                    'benchmark_month_ratio_average']
        table_net_value = Table()
        headers = ["指标", "累加净值", "累乘净值", "基准净值"]
        rows = []
        i = 0
        for key, value in indicator_dict.items():
            data_list = [value,
                         round(self.regression_analysis_obj.net_analysis_result['cumsum'][key], 2),
                         round(self.regression_analysis_obj.net_analysis_result['cumprod'][key], 2),
                         round(self.regression_analysis_obj.net_analysis_result['cumprod'][benchmark_indicator_list[i]],
                               2),
                         ]
            i += 1
            rows.append(data_list)
        table_net_value.add(headers, rows)
        table_net_value.set_global_opts(title_opts=ComponentTitleOpts(title='因子收益率—收益分析'))
        return table_net_value

    def bar_regression_day_profit_ratio(self):
        """
        daily（因子日收益率）
        """
        date_list = list(self.regression_analysis_obj.factor_return.index.astype('str'))
        daily_list = list((self.regression_analysis_obj.factor_return['daily'] * 100).round(2))
        bar_profit_ratio_day = Bar() \
            .add_xaxis(date_list) \
            .add_yaxis("因子日收益率（%）", daily_list) \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-15)),
                             yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(formatter="{value}")),
                             title_opts=opts.TitleOpts(title="因子收益率—因子日收益率"),
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100), )
        return bar_profit_ratio_day

    def bar_regression_day_ratio_distribution(self):
        """
        日收益率分布
        cumsum_net_day_ratio_distribution'（柱状图）
        cumprod_net_day_ratio_distribution'（柱状图）
        benchmark_day_ratio_distribution'（柱状图）
        """
        cumsum_net_day_ratio_distribution_list = list(
            self.regression_analysis_obj.net_analysis_result['cumsum']['net_day_ratio_distribution'].values())
        cumprod_net_day_ratio_distribution_list = list(
            self.regression_analysis_obj.net_analysis_result['cumprod']['net_day_ratio_distribution'].values())

        benchmark_day_ratio_distribution_list = list(
            self.regression_analysis_obj.net_analysis_result['cumsum']['benchmark_day_ratio_distribution'].values())
        bar_day_ratio_distribution = Bar() \
            .add_xaxis(
            list(self.regression_analysis_obj.net_analysis_result['cumsum']['net_day_ratio_distribution'].keys())) \
            .add_yaxis("累加因子净值（%）", [round(i * 100, 2) for i in cumsum_net_day_ratio_distribution_list]) \
            .add_yaxis("累乘因子净值（%）", [round(i * 100, 2) for i in cumprod_net_day_ratio_distribution_list]) \
            .add_yaxis("基准（%）", [round(i * 100, 2) for i in benchmark_day_ratio_distribution_list]) \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-15)),
                             yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(formatter="{value}")),
                             title_opts=opts.TitleOpts(title="因子收益率—日收益率分布"),
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100), )
        return bar_day_ratio_distribution

    def bar_regression_month_profit_ratio(self):
        """
        月度收益率
        cumsum_net_month_ratio_distribution'（柱状图）
        cumprod_benchmark_month_ratio_distribution'（柱状图）
        benchmark_month_ratio'（柱状图）
        """
        cumsum_net_month_ratio_distribution_list = list(
            self.regression_analysis_obj.net_analysis_result['cumsum']['net_month_ratio'].values())
        cumprod_net_ratio_distribution_list = list(
            self.regression_analysis_obj.net_analysis_result['cumprod']['net_month_ratio'].values())
        benchmark_month_ratio_distribution_list = list(
            self.regression_analysis_obj.net_analysis_result['cumprod']['benchmark_month_ratio'].values())
        bar_profit_ratio_month = Bar() \
            .add_xaxis(list(self.regression_analysis_obj.net_analysis_result['cumsum']['net_month_ratio'].keys())) \
            .add_yaxis("累加因子（%）", [round(i, 2) for i in cumsum_net_month_ratio_distribution_list],
                       label_opts=opts.LabelOpts(is_show=False), ) \
            .add_yaxis("累乘因子（%）", [round(i, 2) for i in cumprod_net_ratio_distribution_list],
                       label_opts=opts.LabelOpts(is_show=False), ) \
            .add_yaxis("基准（%）", [round(i, 2) for i in benchmark_month_ratio_distribution_list],
                       label_opts=opts.LabelOpts(is_show=False), ) \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-15)),
                             yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(formatter="{value}")),
                             title_opts=opts.TitleOpts(title="因子收益率—月度收益率"),
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100), )

        return bar_profit_ratio_month

    def table_regression_risk(self):
        """
        风险
        """
        indicator_dict = {'net_year_volatility': "年化波动率（%）",
                          'net_max_drawdown': "历史最大回撤（%）",
                          'net_day_volatility': "日收益率波动率（%）",
                          'net_month_volatility': "月收益率波动率（%）",
                          'downside_risk': "下行风险（%）",
                          'net_skewness': "偏度",
                          'net_kurtosis': "峰度",
                          }
        benchmark_indicator_list = ['benchmark_year_volatility',
                                    'benchmark_max_drawdown',
                                    'benchmark_day_volatility',
                                    'benchmark_month_volatility',
                                    "benchmark_downside_risk",
                                    'benchmark_skewness',
                                    'benchmark_kurtosis',
                                    ]
        table_risk_value = Table()
        headers = ["指标", "累加净值", "累乘净值", "基准净值"]
        rows = []
        i = 0
        for key, value in indicator_dict.items():
            data_list = [value,
                         round(self.regression_analysis_obj.net_analysis_result['cumsum'][key], 2),
                         round(self.regression_analysis_obj.net_analysis_result['cumprod'][key], 2),
                         round(self.regression_analysis_obj.net_analysis_result['cumprod'][benchmark_indicator_list[i]],
                               2),
                         ]
            i += 1
            rows.append(data_list)
        table_risk_value.add(headers, rows)
        table_risk_value.set_global_opts(title_opts=ComponentTitleOpts(title='因子收益率—风险分析'))
        return table_risk_value

    def line_regression_max_drawdown(self):
        """
        风险
        'cumsum_net_value_df'（最大回撤曲线）
        'cumprod_net_value_df'（最大回撤曲线）
        'benchmark_df'（最大回撤）
        """
        cumsum_drawdown_list = list(
            self.regression_analysis_obj.net_analysis_result['cumsum']['net_value_df'].round(2)['drawdown'])
        cumprod_drawdown_list = list(
            self.regression_analysis_obj.net_analysis_result['cumprod']['net_value_df'].round(2)['drawdown'])
        benchmark_drawdown_list = list(
            self.regression_analysis_obj.net_analysis_result['cumsum']['benchmark_df'].round(2)['drawdown'])
        cumsum_net_max_drawdown = round(self.regression_analysis_obj.net_analysis_result['cumsum']['net_max_drawdown'],
                                        2)
        cumprod_net_max_drawdown = round(self.regression_analysis_obj.net_analysis_result['cumsum']['net_max_drawdown'],
                                         2)
        benchmark_max_drawdown = round(
            self.regression_analysis_obj.net_analysis_result['cumsum']['benchmark_max_drawdown'], 2)
        max_drawdown_line = Line() \
            .add_xaxis(
            list(self.regression_analysis_obj.net_analysis_result['cumsum']['net_value_df'].index.astype('str'))) \
            .add_yaxis("累加因子（%）", cumsum_drawdown_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='min')])) \
            .add_yaxis("累乘因子（%）", cumprod_drawdown_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='min')])) \
            .add_yaxis("基准（%）", benchmark_drawdown_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='min')])) \
            .set_series_opts(areastyle_opts=opts.AreaStyleOpts(opacity=0.5),
                             label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(title_opts=opts.TitleOpts(title="因子收益率—最大回撤分析"),
                             # 标题
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),  # 添加竖线信息
                             yaxis_opts=opts.AxisOpts(
                                 min_=int(min(cumsum_net_max_drawdown, cumprod_net_max_drawdown,
                                              benchmark_max_drawdown) * 110) / 100,
                                 max_=0),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100), )  # 设置Y轴范围
        return max_drawdown_line

    # 分层分析
    def line_stratification_net_value(self):
        """
        回归分析 净值图
        """
        benchmark_list = list(
            self.stratification_analysis_obj.group_net_analysis_result['group_0']['benchmark_df']['net_value'].round(4))
        all_list = benchmark_list

        group_net_dict = {}
        for i in range(self.group_num):
            group_net_dict['group_' + str(i)] = \
                list(self.stratification_analysis_obj.group_net_analysis_result['group_' + str(i)]['net_value_df'][
                         'net_value'].round(4))
            all_list = all_list + group_net_dict['group_' + str(i)]

        date_list = list(
            self.stratification_analysis_obj.group_net_analysis_result['group_0']['net_value_df'].index.astype('str'))
        net_value_line = Line() \
            .add_xaxis(date_list) \
            .add_yaxis("基准", benchmark_list)
        for group_name in group_net_dict:
            net_value_line = net_value_line \
                .add_xaxis(date_list) \
                .add_yaxis(group_name, group_net_dict[group_name])

        net_value_line\
            .set_series_opts(areastyle_opts=opts.AreaStyleOpts(opacity=0.1), label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(title_opts=opts.TitleOpts(title="分层分析——净值图",
                                                       subtitle="分为：" + str(self.group_num) + "组"),  # 标题
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),  # 添加竖线信息
                             yaxis_opts=opts.AxisOpts(min_=math.ceil(min(all_list) * 90) / 100,
                                                      max_=int(max(all_list) * 110) / 100),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                             legend_opts=opts.LegendOpts(orient='vertical',
                                                         pos_bottom='bottom',
                                                         pos_top='58px',
                                                         pos_left='right',
                                                         pos_right='right')
                             )  # 设置Y轴范围
        return net_value_line

    def bar_stratification_day_ratio_distribution(self):
        """
        日收益率分布
        benchmark_day_ratio_distribution（柱状图）
        """
        benchmark_day_ratio_distribution_list = list(self.stratification_analysis_obj.
                                                     group_net_analysis_result['group_0']
                                                     ['benchmark_day_ratio_distribution'].values())
        group_day_ratio_distribution_dict = {}
        for i in range(self.group_num):
            group_day_ratio_distribution_dict['group_' + str(i)] = \
                list(self.stratification_analysis_obj.group_net_analysis_result['group_' + str(i)]
                     ['net_day_ratio_distribution'].values())

        date_list = list(self.stratification_analysis_obj.
                         group_net_analysis_result['group_0']['net_day_ratio_distribution'].keys())

        bar_stratification_day_ratio_distribution = Bar() \
            .add_xaxis(date_list) \
            .add_yaxis("基准", [round(i * 100, 2) for i in benchmark_day_ratio_distribution_list])

        for group_name in group_day_ratio_distribution_dict:
            bar_stratification_day_ratio_distribution = bar_stratification_day_ratio_distribution \
                .add_xaxis(date_list) \
                .add_yaxis(group_name, [round(i * 100, 2) for i in group_day_ratio_distribution_dict[group_name]])

        bar_stratification_day_ratio_distribution \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-15)),
                             yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(formatter="{value}")),
                             title_opts=opts.TitleOpts(title="分层分析—日收益率分布（%）"),
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                             legend_opts=opts.LegendOpts(orient='vertical',
                                                         pos_bottom='bottom',
                                                         pos_top='58px',
                                                         pos_left='right',
                                                         pos_right='right'
                                                         ))
        return bar_stratification_day_ratio_distribution

    def bar_stratification_month_profit_ratio(self):
        """
        月度收益率
        benchmark_month_ratio'（柱状图）
        """
        benchmark_month_ratio_list = list(self.stratification_analysis_obj.
                                          group_net_analysis_result['group_0']
                                          ['benchmark_month_ratio'].values())
        group_month_ratio_dict = {}
        for i in range(self.group_num):
            group_month_ratio_dict['group_' + str(i)] = \
                list(self.stratification_analysis_obj.group_net_analysis_result['group_' + str(i)]
                     ['net_month_ratio'].values())

        date_list = list(self.stratification_analysis_obj.
                         group_net_analysis_result['group_0']['net_month_ratio'].keys())

        bar_stratification_month_profit_ratio = Bar() \
            .add_xaxis(date_list) \
            .add_yaxis("基准", [round(i, 2) for i in benchmark_month_ratio_list])
        for group_name in group_month_ratio_dict:
            bar_stratification_month_profit_ratio = bar_stratification_month_profit_ratio \
                .add_xaxis(date_list) \
                .add_yaxis(group_name, [round(i * 100, 2) for i in group_month_ratio_dict[group_name]])

        bar_stratification_month_profit_ratio \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False)) \
            .set_global_opts(xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-15)),
                             yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(formatter="{value}")),
                             title_opts=opts.TitleOpts(title="分层分析—月度收益率（%）"),
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                             legend_opts=opts.LegendOpts(orient='vertical',
                                                         pos_bottom='bottom',
                                                         pos_top='58px',
                                                         pos_left='right',
                                                         pos_right='right'
                                                         ))
        return bar_stratification_month_profit_ratio

    def table_stratification_risk(self):
        """
        风险
        """
        indicator_dict = {'net_year_volatility': "年化波动率（%）",
                          'net_max_drawdown': "历史最大回撤（%）",
                          'net_day_volatility': "日收益率波动率（%）",
                          'net_month_volatility': "月收益率波动率（%）",
                          'downside_risk': "下行风险（%）",
                          'net_skewness': "偏度",
                          'net_kurtosis': "峰度",
                          }
        benchmark_indicator_list = ['benchmark_year_volatility',
                                    'benchmark_max_drawdown',
                                    'benchmark_day_volatility',
                                    'benchmark_month_volatility',
                                    "benchmark_downside_risk",
                                    'benchmark_skewness',
                                    'benchmark_kurtosis',
                                    ]
        table_stratification_risk = Table()
        headers = ["指标"] + ['group_' + str(i) for i in range(self.group_num)] + ["基准净值"]
        rows = []
        indicator_num = 0
        for key, value in indicator_dict.items():
            data_list = [value] + \
                        [round(self.stratification_analysis_obj.group_net_analysis_result['group_' + str(i)][key], 2)
                         for i in range(self.group_num)] + \
                        [round(self.stratification_analysis_obj.group_net_analysis_result['group_0'][
                                   benchmark_indicator_list[indicator_num]], 2)]
            indicator_num += 1
            rows.append(data_list)
        table_stratification_risk.add(headers, rows)
        table_stratification_risk.set_global_opts(title_opts=ComponentTitleOpts(title='分层分析—风险分析'))
        return table_stratification_risk

    def line_stratification_max_drawdown(self):
        """
        风险
        'benchmark_df'（最大回撤）
        """
        benchmark_drawdown_list = list(
            self.stratification_analysis_obj.group_net_analysis_result['group_0']['benchmark_df']['drawdown'].round(2))
        all_list = benchmark_drawdown_list

        group_max_drawdown_dict = {}
        for i in range(self.group_num):
            group_max_drawdown_dict['group_' + str(i)] = \
                list(self.stratification_analysis_obj.group_net_analysis_result['group_' + str(i)]['net_value_df'][
                         'drawdown'].round(2))
            all_list = all_list + group_max_drawdown_dict['group_' + str(i)]

        date_list = list(
            self.stratification_analysis_obj.group_net_analysis_result['group_0']['net_value_df'].index.astype('str'))

        line_stratification_max_drawdown = Line() \
            .add_xaxis(date_list) \
            .add_yaxis("基准", benchmark_drawdown_list,
                       markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='min')])) \
            .set_global_opts(title_opts=opts.TitleOpts(title="分层分析—最大回撤分析（%）"),
                             # 标题
                             tooltip_opts=opts.TooltipOpts(trigger="axis"),  # 添加竖线信息
                             yaxis_opts=opts.AxisOpts(
                                 min_=int(min(all_list) * 110) / 100,
                                 max_=0),
                             datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                             legend_opts=opts.LegendOpts(orient='vertical',
                                                         pos_bottom='bottom',
                                                         pos_top='58px',
                                                         pos_left='right',
                                                         pos_right='-15px'
                                                         ))  # 设置Y轴范围
        for group_name in group_max_drawdown_dict:
            line_stratification_max_drawdown = line_stratification_max_drawdown \
                .add_xaxis(date_list) \
                .add_yaxis(group_name, group_max_drawdown_dict[group_name],
                           markpoint_opts=opts.MarkPointOpts(data=[opts.MarkPointItem(type_='min')]))

        line_stratification_max_drawdown.set_series_opts(areastyle_opts=opts.AreaStyleOpts(opacity=0.5),
                                                         label_opts=opts.LabelOpts(is_show=False))
        return line_stratification_max_drawdown

    def show_page(self):
        page = Page(page_title='因子评价报告')

        table_factor_information = self.table_factor_information()
        page.add(table_factor_information)
        # IC分析
        table_ic_result = self.table_ic_result()
        page.add(table_ic_result)

        bar_ic = self.bar_ic()
        page.add(bar_ic)

        bar_ic_p_value = self.bar_ic_p_value()
        page.add(bar_ic_p_value)
        # 回归分析
        line_regression_net_value = self.line_regression_net_value()
        page.add(line_regression_net_value)

        bar_regression_t_value = self.bar_regression_t_value()
        page.add(bar_regression_t_value)

        table_regression_net_value = self.table_regression_net_value()
        page.add(table_regression_net_value)

        bar_regression_day_profit_ratio = self.bar_regression_day_profit_ratio()
        page.add(bar_regression_day_profit_ratio)

        bar_regression_day_ratio_distribution = self.bar_regression_day_ratio_distribution()
        page.add(bar_regression_day_ratio_distribution)

        bar_regression_month_profit_ratio = self.bar_regression_month_profit_ratio()
        page.add(bar_regression_month_profit_ratio)

        table_regression_risk = self.table_regression_risk()
        page.add(table_regression_risk)

        line_regression_max_drawdown = self.line_regression_max_drawdown()
        page.add(line_regression_max_drawdown)

        # 分层分析
        line_stratification_net_value = self.line_stratification_net_value()
        page.add(line_stratification_net_value)

        bar_stratification_day_ratio_distribution = self.bar_stratification_day_ratio_distribution()
        page.add(bar_stratification_day_ratio_distribution)

        bar_stratification_month_profit_ratio = self.bar_stratification_month_profit_ratio()
        page.add(bar_stratification_month_profit_ratio)

        table_stratification_risk = self.table_stratification_risk()
        page.add(table_stratification_risk)

        line_stratification_max_drawdown = self.line_stratification_max_drawdown()
        page.add(line_stratification_max_drawdown)

        page.render(self.path + self.factor_name + "_因子评价报告.html")


if __name__ == '__main__':
    factor_name = 'factor_daily_std'
    save_get_factor = SaveGetFactor()
    factor_ma5 = save_get_factor.get_factor(factor_name, factor_name + '_pre')

    factor_ma5 = factor_ma5[factor_ma5.index >= datetime(2015, 2, 1)]
    factor_ma5 = factor_ma5[factor_ma5.index < datetime(2023, 4, 1)]
    # factor_ma5 = factor_ma5.iloc[:-50, :]

    path = LocalDataPath.path + LocalDataFolderName.FACTOR.value + '/' + factor_name+ '/'

    factor_analysis_obj = FactorAnalysis(factor_ma5, factor_name, path)
    print('-' * 20, 'ic_analysis', '-' * 20)
    ic_analysis_obj = factor_analysis_obj.ic_analysis()
    print('-' * 20, 'regression_analysis', '-' * 20)
    regression_analysis_obj = factor_analysis_obj.regression_analysis()
    print('-' * 20, 'stratification_analysis', '-' * 20)
    stratification_analysis_obj = factor_analysis_obj.stratification_analysis()
    factor_analysis_obj.show_page()
