from collections import defaultdict, deque
from shioaji import BidAskFOPv1, Exchange
import shioaji as sj
import datetime
import pandas as pd
import talib as ta
import time
from math import ceil
import pytrader as pyt
from backtesting.lib import crossover

api = sj.Shioaji(simulation=True)
accounts = api.login(
    api_key="3WmNiNGCQMuPGsRMdpgML3MWYkqM1gExzPUGKKcjhufd",     # 請修改此處
    secret_key="EnKAve1Ldd8wuerMRcwKUUrB4DRmLyoxCSyoApmbzrTM"   
)

# 輸入學號、API_KEY、SECRET_KEY
trader = pyt.pytrader(strategy='108062313', api_key="3WmNiNGCQMuPGsRMdpgML3MWYkqM1gExzPUGKKcjhufd", secret_key="EnKAve1Ldd8wuerMRcwKUUrB4DRmLyoxCSyoApmbzrTM") 
# # 設定商品
trader.contract('TXF')

contract = min(
    [
        x for x in api.Contracts.Futures.TXF
        if x.code[-2:] not in ["R1", "R2"]
    ],
    key=lambda x: x.delivery_date
)

msg_queue = defaultdict(deque)
api.set_context(msg_queue)


@api.on_bidask_fop_v1(bind=True)
def quote_callback(self, exchange: Exchange, bidask: BidAskFOPv1):
    # append quote to message queue
    self['bidask'].append(bidask)


api.quote.subscribe(
    contract,
    quote_type=sj.constant.QuoteType.BidAsk,
    version=sj.constant.QuoteVersion.v1
)

time.sleep(2.5)

# get maximum strategy kbars to dataframe, extra 30 it's for safety
bars = 65 + 30

# since every day has 60 kbars (only from 8:45 to 13:45), for 5 minuts kbars
days = ceil(bars/60)

df_5min = []
while(len(df_5min) < bars):
    kbars = api.kbars(
        contract=api.Contracts.Futures.TXF.TXFR1,
        start=(datetime.date.today() -
               datetime.timedelta(days=days)).strftime("%Y-%m-%d"),
        end=datetime.date.today().strftime("%Y-%m-%d"),
    )
    df = pd.DataFrame({**kbars})
    df.ts = pd.to_datetime(df.ts)
    df = df.set_index('ts')
    df.index.name = None
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    df = df.between_time('08:44:00', '13:45:01')
    df_5min = df.resample('5T', label='right', closed='right').agg(
        {'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
         })
    df_5min.dropna(axis=0, inplace=True)
    days += 1

ts = datetime.datetime.now()

while datetime.datetime.now().time() < datetime.time(13, 40):
    time.sleep(1)
    
    # this place can add stop or limit order
    if(len(trader.position) == 0):
        self_position = 'None'
    else:
        self_position = 'Buy' if trader.position['is_long'] else 'Sell'
    
    if self_position == 'Buy':    
        if trader.position['pnl'] < -200 * 50: # 50 point stop loss
            trader.sell(size = 1)
    if self_position == 'Sell':    
        if trader.position['pnl'] < -200 * 50: # 50 point stop loss
            trader.buy(size = 1)

    # local time > next kbars time
    if(datetime.datetime.now() >= ts):

        kbars = api.kbars(
            contract=api.Contracts.Futures.TXF.TXFR1,
            start=datetime.date.today().strftime("%Y-%m-%d"),
            end=datetime.date.today().strftime("%Y-%m-%d"),
        )
        df = pd.DataFrame({**kbars})
        df.ts = pd.to_datetime(df.ts)
        df = df.set_index('ts')
        df.index.name = None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df = df.between_time('08:44:00', '13:45:01')
        df = df.resample('5T', label='right', closed='right').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'})
        df.dropna(axis=0, inplace=True)
        df_5min.update(df)
        to_be_added = df.loc[df.index.difference(df_5min.index)]
        df_5min = pd.concat([df_5min, to_be_added])
        ts = df_5min.iloc[-1].name.to_pydatetime()

        # next kbar time update and local time < next kbar time
        if (datetime.datetime.now().minute != ts.minute):

            df_5min = df_5min[:-1]

            WL = 65
            OB = -15
            OS = -80
            L = 3
            
            n1 = 15
            n2 = 55

            self_wl = ta.WILLR(
                df_5min['High'], df_5min['Low'], df_5min['Close'], WL)
            self_min = ta.MIN(df_5min['Low'], L)
            self_max = ta.MAX(df_5min['High'], L)
            self_sma1 = ta.SMA(df_5min['Close'], n1) # sma 快線
            self_sma2 = ta.SMA(df_5min['Close'], n2) # sma 慢線
            
            condition1 = datetime.datetime.now().time() < datetime.time(13, 25)
            condition2 = datetime.datetime.now().time() > datetime.time(9, 0)

#             condition1 = datetime.datetime.now().time() < time(13, 25)
#             condition2 = datetime.datetime.now().time() > time(9, 0)
#             condition3 = (self_wl[-2] < OB) and (self_wl[-1] > OB)
#             condition4 = (self_wl[-2] > OB) and (self_wl[-1] < OB)
#             condition5 = df_5min['Close'][-1] <= self_min[-1]
#             condition6 = datetime.datetime.now().time() >= time(13, 25)
            
            long_condition1 = (self_wl[-2] < OB) and (self_wl[-1] > OB) # WR多單進場
            long_condition2 = self_wl[-2] > OB and self_wl[-1] < OB #WR跌出超買區
            long_condition3 = df_5min['Close'][-1] <= self_min[-1] #跌破3根低點停利停損
#             long_condition4 = self.position.pl_pct < -(self.stop_pct * 0.001) #百分比停損
            long_condition5 = crossover(self_sma1 , self_sma2) #sma 快線 cross over sma 慢線 -> buy
            long_condition6 = crossover(self_sma2 , self_sma1) #sma 慢線 cross over sma 快線 -> sell
            
            if(len(trader.position) == 0):
                self_position = 'None'
            else:
                self_position = 'Buy' if trader.position['is_long'] else 'Sell'
            

            if self_position == 'None':
                if condition1 and condition2:
                    if long_condition1 or long_condition5:
                        trader.buy(size = 1)

            elif self_position == 'Buy':
                if long_condition2:
                    trader.sell(size = 1)        
                if long_condition3:
                    trader.sell(size = 1)        
                if long_condition6:
                    trader.sell(size = 1)        
                    
#           ============================

            short_condition1 = (self_wl[-2] > OS) and (self_wl[-1] < OS)# WR空單進場
            short_condition2 = self_wl[-2] < OS and self_wl[-1] > OS #WR向上超出超賣區
            short_condition3 = df_5min['Close'][-1] >= self_max[-1] #超出3根高點停利停損
#             short_condition4 = self.position.pl_pct < -(self.stop_pct * 0.001) #百分比停損
            short_condition5 = crossover(self_sma1 , self_sma2) #sma 快線 cross over sma 慢線 -> sell
            short_condition6 = crossover(self_sma2 , self_sma1) #sma 慢線 cross over sma 快線 -> buy
            
            if self_position == 'None':
                if condition1 and condition2:
                    if short_condition1 or short_condition6:
                        trader.sell(size = 1)

            elif self_position == 'Sell':
                if short_condition2:
                    trader.buy(size = 1)
                if short_condition3:
                    trader.buy(size = 1)
                if short_condition5:
                    trader.buy(size = 1)


api.quote.unsubscribe(
    contract,
    quote_type=sj.constant.QuoteType.BidAsk,
    version=sj.constant.QuoteVersion.v1
)

api.logout()
