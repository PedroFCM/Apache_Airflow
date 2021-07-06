from airflow.models import DAG
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.postgres_hook import PostgresHook

from datetime import datetime
from pandas import json_normalize, DataFrame
import json
from contextlib import closing

default_args = {
    'start_date': datetime(2020, 1, 1)
}

def _process_data(ti):
    data_initial = ti.xcom_pull(task_ids = ['get_data'])

    if not len(data_initial) or 'results' not in data_initial[0]:
        raise ValueError('Data is empty')

    print(data_initial[0]['results'])

    df = DataFrame(columns = ['city', 'country', 'count', 'parameters'])

    for i in range(len(data_initial[0]['results'])):
        data = data_initial[0]['results'][i]
        
        params = str(data['parameters'])
        params = params.replace('[', '{')
        params = params.replace(']', '}')

        processed_data = json_normalize({'city': data['city'],
                                        'country': data['country'],
                                        'count': data['count'],
                                        'parameters': params})

        df = df.append(processed_data, ignore_index = True)

    print('Final Dataframe:')
    print(df)
    df.to_csv('/tmp/processed_data.csv', index = None, header = False, sep = ';')
    

def _storing():    
    # Open Postgres Connection
    with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
            with closing(conn.cursor()) as cur:
                # CSV loading to table.
                copy_sql = '''COPY open_aq (city, country, count, parameters) FROM '/tmp/processed_data.csv' DELIMITER ';' CSV;'''
                
                cur.itersize = 1000
                cur.execute(copy_sql)
                conn.commit()


with DAG('open_aq', schedule_interval = '@daily', 
         default_args = default_args, catchup = False) as dag:

    drop_table = PostgresOperator(task_id = 'drop_table',
                                  postgres_conn_id = 'postgres_default',
                                  sql = '''DROP TABLE IF EXISTS open_aq''')

    create_table = PostgresOperator(task_id = 'create_table',
                                    postgres_conn_id = 'postgres_default',
                                    sql = '''CREATE TABLE open_aq (
                                        id SERIAL PRIMARY KEY,
                                        city VARCHAR NOT NULL,
                                        country VARCHAR NOT NULL,
                                        count INT NOT NULL,
                                        parameters VARCHAR ARRAY);''')

    parameters = {
        'country': 'PT'
    }

    is_API_available = HttpSensor(task_id = 'is_API_available', 
                                  http_conn_id = 'open_aq_api',
                                  endpoint = 'v2/cities',
                                  request_params = parameters)
    
    get_data = SimpleHttpOperator(task_id = 'get_data', 
                                  http_conn_id = 'open_aq_api',
                                  endpoint = 'v2/cities',
                                  data = parameters,
                                  method = 'GET',
                                  response_filter = lambda response: json.loads(response.text),
                                  log_response = True)

    process_data = PythonOperator(task_id = 'process_data',
                                  python_callable = _process_data)

    store_data = PythonOperator(task_id = 'store_data',
                                python_callable = _storing)

    drop_table >> create_table >> is_API_available >> get_data >> process_data >> store_data 

    