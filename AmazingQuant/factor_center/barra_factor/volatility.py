# -*- coding: utf-8 -*-

# ------------------------------
# @Time    : 2024/1/7
# @Author  : gao
# @File    : volatility.py
# @Project : AmazingQuant
# ------------------------------
import datetime

import talib
import pandas as pd
import numpy as np

from AmazingQuant.factor_center.save_get_factor import SaveGetFactor
from AmazingQuant.constant import RightsAdjustment
from AmazingQuant.data_center.api_data.get_kline import GetKlineData


class FactorVolatility(object):
    def __init__(self, start_date, end_date):
        self.close_df = None
        self.index_close_df = None
        self.start_date = start_date
        self.end_date = end_date
        self.save_get_factor = SaveGetFactor()

    def cache_data(self):
        kline_object = GetKlineData()
        all_market_data = kline_object.cache_all_stock_data(dividend_type=RightsAdjustment.FROWARD.value)
        self.close_df = all_market_data['close'].loc[self.start_date: self.end_date]

        all_index_data = kline_object.cache_all_index_data()
        self.index_close_df = all_index_data['close'].loc[self.start_date: self.end_date]

    def factor_beta(self, index_code='000300.SH'):
        # BETA（三级因子）:股票收益率对沪深300收益率进行时间序列回归，取回归系数，回归时间窗口为252个交易日，半衰期63个交易日。
        window, half_life = 252, 63
        L, Lambda = 0.5 ** (1 / half_life), 0.5 ** (1 / half_life)
        W = []
        for i in range(window):
            W.append(Lambda)
            Lambda *= L
        W = W[::-1]
        index_close_df = self.index_close_df[index_code]
        index_ratio_df = index_close_df.pct_change()*100
        index_ratio_df = index_ratio_df.iloc[1:]
        ratio_df = self.close_df.pct_change()*100
        ratio_df = ratio_df.iloc[1:, :]
        beta_full_list = []
        hist_sigma_list = []
        for i in range(index_ratio_df.shape[0]-window+1):
            tmp = ratio_df.iloc[i:i+window, :].copy()
            W_full = np.diag(W)
            Y_full = tmp.dropna(axis=1)
            idx_full, Y_full = Y_full.columns, Y_full.values
            X_full = np.c_[np.ones((window, 1)), index_ratio_df.iloc[i:i+window].values]

            beta_full = np.linalg.pinv(X_full.T @ W_full @ X_full) @ X_full.T @ W_full @ Y_full

            hist_sigma_full = pd.DataFrame(np.std(Y_full - X_full @ beta_full, axis=0), index=idx_full,
                                           columns=[tmp.index[-1]]).T
            hist_sigma_list.append(hist_sigma_full)

            beta_full = pd.DataFrame(beta_full[1], index=idx_full, columns=[tmp.index[-1]]).T
            beta_full_list.append(beta_full)
            print(tmp.index[-1])

        beta_df = pd.concat(beta_full_list)
        hist_sigma_df = pd.concat(hist_sigma_list)
        return beta_df, hist_sigma_df

    def factor_daily_std(self):
        ratio_df = self.close_df.pct_change() * 100
        window, half_life = 252, 42
        L, Lambda = 0.5 ** (1 / half_life), 0.5 ** (1 / half_life)
        W = []
        for i in range(window):
            W.append(Lambda)
            Lambda *= L
        W.reverse()
        W_sum = sum(W)
        W_ratio = [i / W_sum for i in W]

        daily_std_list = []
        for i in range(ratio_df.shape[0]-window):
            W_ratio_df = pd.Series(W_ratio, index=ratio_df.iloc[i: i+window].index)
            ratio_weighted = ratio_df.iloc[i: i+window].mul(W_ratio_df, axis=0)
            ratio_weighted_std = ratio_weighted.std()
            ratio_weighted_std.name = ratio_weighted.index[-1]
            daily_std_list.append(ratio_weighted_std)

        daily_std_df = pd.concat(daily_std_list, axis=1).T

        return daily_std_df

    def save_factor_data(self, file_name, factor_name, factor_data):
        self.save_get_factor.save_factor(file_name, factor_name, factor_data)


if __name__ == '__main__':
    start_date = datetime.datetime(2015, 10, 1)
    end_date = datetime.datetime(2024, 1, 1)
    factor_volatility_object = FactorVolatility(start_date, end_date)
    factor_volatility_object.cache_data()
    # beta_df, hist_sigma_df = factor_volatility_object.factor_beta()
    # factor_volatility_object.save_factor_data('factor_beta', 'factor_beta', beta_df)
    # factor_volatility_object.save_factor_data('factor_hist_sigma', 'factor_hist_sigma', hist_sigma_df)
    daily_std_df = factor_volatility_object.factor_daily_std()
    factor_volatility_object.save_factor_data('factor_daily_std', 'factor_daily_std', daily_std_df)
