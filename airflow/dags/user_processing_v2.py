from airflow.models import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.postgres_hook import PostgresHook

from datetime import datetime
from pandas import json_normalize
import json
from contextlib import closing

NUMBER_USERS = 5

default_args = {
    'start_date': datetime(2020, 1, 1)
}

def _processing_user(*op_args, task_instance):
    users = task_instance.xcom_pull(task_ids = ['extracting_user_{}'.format(op_args[0])])

    if not len(users) or 'results' not in users[0]:
        raise ValueError('User is empty')
    
    user = users[0]['results'][0]

    processed_user = json_normalize({'first_name': user['name']['first'],
                                     'last_name': user['name']['last'],
                                     'country': user['location']['country'],
                                     'username': user['login']['username'],
                                     'password': user['login']['password'],
                                     'email': user['email']})
    
    return processed_user.to_json(orient = 'records')

def _storing(ti):
    for i in range(NUMBER_USERS):
        processing_user = ti.xcom_pull(task_ids = ['processing_user_{}'.format(i + 1)])
        processing_user = json.loads(processing_user[0].replace('[', '').replace(']', ''))
        
        print('Processing user', processing_user)

        # Open Postgres Connection
        with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
                with closing(conn.cursor()) as cur:
                    # CSV loading to table.
                    copy_sql = '''INSERT INTO users VALUES (%s, %s, %s, %s, %s, %s);'''

                    cur.itersize = 1000
                    cur.execute(copy_sql, (processing_user['first_name'], processing_user['last_name'],
                            processing_user['country'], processing_user['username'], processing_user['password'], 
                            processing_user['email']) )

                    conn.commit()
    

with DAG('user_processing_v2', schedule_interval = '@daily', 
         default_args = default_args, catchup = False) as dag:
    # Define tasks/operators
    creating_table = PostgresOperator(task_id = 'creating_table',
                                      postgres_conn_id = 'postgres_default',
                                      sql = ''' CREATE TABLE IF NOT EXISTS users (
                                          first_name VARCHAR NOT NULL,
                                          last_name VARCHAR NOT NULL,
                                          country VARCHAR NOT NULL,
                                          username VARCHAR NOT NULL,
                                          password VARCHAR NOT NULL,
                                          email VARCHAR NOT NULL PRIMARY KEY); ''')

    is_api_available = HttpSensor(task_id = 'is_api_available', 
                                  http_conn_id = 'user_api',
                                  endpoint = 'api/')
    
    storing_user = PythonOperator(task_id = 'store_data', 
                                  python_callable = _storing)

    for i in range(NUMBER_USERS):
        extracting_user = SimpleHttpOperator(task_id = 'extracting_user_{}'.format(i + 1), 
                                             http_conn_id = 'user_api', 
                                             endpoint = 'api/', 
                                             method = 'GET',
                                             response_filter = lambda response: json.loads(response.text),
                                             log_response = True)

        processing_user = PythonOperator(task_id = 'processing_user_{}'.format(i + 1), 
                                         python_callable = _processing_user, 
                                         op_args = [i + 1])
    
        is_api_available >> extracting_user >> processing_user >> storing_user

    creating_table >> is_api_available