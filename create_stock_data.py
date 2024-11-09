import yfinance as yf
import os
import pandas as pd

spx_const = pd.read_csv('data/SPXconst.csv')

#Make datetime and make sure its D/M/Y
spx_const.columns = pd.to_datetime(spx_const.columns, dayfirst=True)


# Loop over each year from 1990 to 2018 (2019 so it actually runs 2018)
for year in range(1990, 2019):
    start_date = f"{year}-01-01"
    end_date = f"{year + 4}-01-01"

    # SET for uniqueness
    tickers = set()
    for month in range(1, 13):
        date_col = pd.to_datetime(f"{year}-{month:02d}-01")
        if date_col in spx_const.columns:
            #Make sure to remove NAN with dropna and grab new values wiht unique
            tickers.update(spx_const[date_col].dropna().unique())

    data = yf.download(list(tickers), start=start_date, end=end_date, group_by='ticker')

    op = pd.DataFrame({ticker: pd.to_numeric(data[ticker]['Open'], errors='coerce').ffill().fillna(0) for ticker in tickers})
    cp = pd.DataFrame({ticker: pd.to_numeric(data[ticker]['Close'], errors='coerce').ffill().fillna(0) for ticker in tickers})

    #Need this for formatting correctness
    op.index = pd.to_datetime(op.index).strftime('%Y-%m-%d')
    cp.index = pd.to_datetime(cp.index).strftime('%Y-%m-%d')

    #AVOID DIV BY 0
    op.replace(0, 3, inplace=True)

    #Make sure we have the data in the YMD format in the first column
    op.reset_index(inplace=True)
    cp.reset_index(inplace=True)
    op.rename(columns={'index': 'Date'}, inplace=True)
    cp.rename(columns={'index': 'Date'}, inplace=True)


    op.to_csv(f"data/Open-{year}.csv", index=False)
    cp.to_csv(f"data/Close-{year}.csv", index=False)


