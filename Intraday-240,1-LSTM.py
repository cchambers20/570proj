import pandas as pd
import numpy as np
import random
import time
import pickle
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import RobustScaler
from Statistics import Statistics

import tensorflow as tf
from tensorflow.keras.layers import LSTM, Dropout,Dense,Input,add
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau, CSVLogger, LearningRateScheduler
from tensorflow.keras.models import Model, Sequential, load_model
from tensorflow.keras import optimizers
import warnings
warnings.filterwarnings("ignore")

import os
SEED = 9
os.environ['PYTHONHASHSEED']=str(SEED)
random.seed(SEED)
np.random.seed(SEED)


SP500_df = pd.read_csv('data/SPXconst.csv')
all_companies = list(set(SP500_df.values.flatten()))
#all_companies.remove(np.nan)

constituents = {'-'.join(col.split('/')[::-1]):set(SP500_df[col].dropna()) 
                for col in SP500_df.columns}

constituents_train = {} 
for test_year in range(1993,2016):
    months = [str(t)+'-0'+str(m) if m<10 else str(t)+'-'+str(m) 
              for t in range(test_year-3,test_year) for m in range(1,13)]
    constituents_train[test_year] = [list(constituents[m]) for m in months]
    constituents_train[test_year] = set([i for sublist in constituents_train[test_year] 
                                         for i in sublist])

def makeLSTM():
    inputs = Input(shape=(240,1))
    #Change, as CUDALSTM no longer a "thing"
    x = LSTM(25, return_sequences=False, recurrent_activation='sigmoid')(inputs)
    x = Dropout(0.1)(x)
    outputs = Dense(2,activation='softmax')(x)
    model = Model(inputs=inputs, outputs=outputs)
    model.compile(loss='categorical_crossentropy',optimizer=optimizers.RMSprop(),
                          metrics=['accuracy'])
    model.summary()
    return model
    

def callbacks_req(model_type='LSTM'):
    csv_logger = CSVLogger(model_folder+'/training-log-'+model_type+'-'+str(test_year)+'.csv')
    filepath = model_folder+"/model-" + model_type + '-' + str(test_year) + "-E{epoch:02d}.keras" #Changed to kearas

    model_checkpoint = ModelCheckpoint(filepath, monitor='val_loss', save_best_only=False, save_freq='epoch')


    earlyStopping = EarlyStopping(monitor='val_loss',mode='min',patience=10,restore_best_weights=True)
    return [csv_logger,earlyStopping,model_checkpoint]

def reshaper(arr):
    arr = np.array(np.split(arr,3,axis=1))
    arr = np.swapaxes(arr,0,1)
    arr = np.swapaxes(arr,1,2)
    return arr

def trainer(train_data, test_data, model_type='LSTM'):
    np.random.shuffle(train_data)
    train_x, train_y, train_ret = train_data[:, 2:-2], train_data[:, -1], train_data[:, -2]
    train_x = np.reshape(train_x, (len(train_x), 240, 1))
    train_y = np.reshape(train_y, (-1, 1))

    enc = OneHotEncoder(handle_unknown='ignore')
    enc.fit(train_y)
    enc_y = enc.transform(train_y).toarray()

    #Fix issues with varying data type, ENSURE float
    train_x = np.nan_to_num(train_x).astype('float32')
    enc_y = np.nan_to_num(enc_y).astype('float32')

    if model_type == 'LSTM':
        model = makeLSTM()
    else:
        return

    callbacks = callbacks_req(model_type)

    model.fit(
        train_x,
        enc_y,
        epochs=5,
        validation_split=0.2,
        callbacks=callbacks,
        batch_size=512
    )

    dates = list(set(test_data[:, 0]))
    predictions = {}

    for day in dates:
        test_d = test_data[test_data[:, 0] == day]
        test_d = test_d[:, 2:-2]

        # Handle NaN/infinite values and ensure numeric type
        test_d = np.nan_to_num(test_d).astype('float32')

        # Reshape test_d to 3D (required by LSTM model)
        if test_d.ndim == 2:
            test_d = np.reshape(test_d, (len(test_d), 240, 1))


        # Make predictions
        predictions[day] = model.predict(test_d)[:, 1]

    return model, predictions


def trained(filename, train_data, test_data):
    model = load_model(filename)

    dates = list(set(test_data[:, 0]))
    predictions = {}

    for day in dates:
        test_d = test_data[test_data[:, 0] == day]
        test_d = test_d[:, 2:-2]

        # Handle NaN/infinite values and ensure numeric type
        test_d = np.nan_to_num(test_d).astype('float32')

        # Reshape test_d to 3D (required by LSTM model)
        if test_d.ndim == 2:
            test_d = np.reshape(test_d, (len(test_d), 240, 1))



        # Make predictions
        predictions[day] = model.predict(test_d)[:, 1]

    return model, predictions
  

def simulate(test_data,predictions):
    rets = pd.DataFrame([],columns=['Long','Short'])
    k = 10
    for day in sorted(predictions.keys()):
        preds = predictions[day]
        test_returns = test_data[test_data[:,0]==day][:,-2]
        top_preds = predictions[day].argsort()[-k:][::-1] 
        trans_long = test_returns[top_preds]
        worst_preds = predictions[day].argsort()[:k][::-1] 
        trans_short = -test_returns[worst_preds]
        rets.loc[day] = [np.mean(trans_long),np.mean(trans_short)] 
    print('Result : ',rets.mean())  
    return rets       

    
def create_label(df_open,df_close,perc=[0.5,0.5]):
    if not np.all(df_close.iloc[:,0]==df_open.iloc[:,0]):
        print('Date Index issue')
        return
    perc = [0.]+list(np.cumsum(perc))
    label = (df_close.iloc[:,1:]/df_open.iloc[:,1:]-1).apply(
            lambda x: pd.qcut(x.rank(method='first'),perc,labels=False), axis=1)
    return label[1:]

def create_stock_data(df_open,df_close,st,m=240):
    st_data = pd.DataFrame([])
    st_data['Date'] = list(df_close['Date'])
    st_data['Name'] = [st]*len(st_data)
    daily_change = df_close[st]/df_open[st]-1
    for k in range(m)[::-1]:
        st_data['IntraR'+str(k)] = daily_change.shift(k)

    st_data['IntraR-future'] = daily_change.shift(-1)    
    st_data['label'] = list(label[st])+[np.nan] 
    st_data['Month'] = list(df_close['Date'].str[:-3])
    st_data = st_data.dropna()
    
    trade_year = st_data['Month'].str[:4]
    st_data = st_data.drop(columns=['Month'])
    st_train_data = st_data[trade_year<str(test_year)]
    st_test_data = st_data[trade_year==str(test_year)]
    return np.array(st_train_data),np.array(st_test_data) 

def scalar_normalize(train_data,test_data):
    scaler = RobustScaler()
    scaler.fit(train_data[:,2:-2])
    train_data[:,2:-2] = scaler.transform(train_data[:,2:-2])
    test_data[:,2:-2] = scaler.transform(test_data[:,2:-2])
    

model_folder = 'models-Intraday-240-1-LSTM'
result_folder = 'results-Intraday-240-1-LSTM'
for directory in [model_folder,result_folder]:
    if not os.path.exists(directory):
        os.makedirs(directory)

for test_year in range(1993,2020):
    
    print('-'*40)
    print(test_year)
    print('-'*40)
    
    filename = 'data/Open-'+str(test_year-3)+'.csv'
    df_open = pd.read_csv(filename)
    filename = 'data/Close-'+str(test_year-3)+'.csv'
    df_close = pd.read_csv(filename)
    
    label = create_label(df_open,df_close)
    stock_names = sorted(list(constituents[str(test_year-1)+'-12']))
    train_data,test_data = [],[]

    start = time.time()
    for st in stock_names:
        st_train_data,st_test_data = create_stock_data(df_open,df_close,st)
        train_data.append(st_train_data)
        test_data.append(st_test_data)
        
    train_data = np.concatenate([x for x in train_data])
    test_data = np.concatenate([x for x in test_data])
    
    scalar_normalize(train_data,test_data)
    print(train_data.shape,test_data.shape,time.time()-start)
    
    model,predictions = trainer(train_data,test_data)
    returns = simulate(test_data,predictions)
    returns.to_csv(result_folder+'/avg_daily_rets-'+str(test_year)+'.csv')
    
    result = Statistics(returns.sum(axis=1))
    print('\nAverage returns prior to transaction charges')
    result.shortreport() 
    
    with open(result_folder+"/avg_returns.txt", "a") as myfile:
        res = '-'*30 + '\n'
        res += str(test_year) + '\n'
        res += 'Mean = ' + str(result.mean()) + '\n'
        res += 'Sharpe = '+str(result.sharpe()) + '\n'
        res += '-'*30 + '\n'
        myfile.write(res)
        

