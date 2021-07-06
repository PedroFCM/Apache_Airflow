from airflow.models import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.postgres_hook import PostgresHook

from datetime import datetime
from pandas import json_normalize, read_json
import json
from contextlib import closing

default_args = {
    'start_date': datetime(2020, 1, 1)
}

def _get_users():
    # Open Postgres Connection
    with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
        with closing(conn.cursor()) as cursor:
            sql = '''SELECT 
                json_agg(p) 
                FROM (SELECT * FROM PATIENT LIMIT 20) AS p;'''

            # Executes the sql
            cursor.execute(sql)
            # Fetch all the data from the executed request
            sources = cursor.fetchall()
            #sources = str(sources[0]).replace('RealDictRow', '')[15:][:-3]
            print(sources)

        return str(sources)

def _users_treatment(ti):
    users = ti.xcom_pull(task_ids = ['get_users'])

    users = str(users[0]).replace('RealDictRow', '')[15:][:-4]
    print(users)
    users = json.dumps(users)
    print(users)
    
    users = json.loads(users)
    users = str(users).replace('\'', '"')
    users = users.replace('None', '{}')
    users = users.replace('False', 'false')
    users = users.replace('True', 'true')
    print('Users:', users)

    return users

def _write_users(ti):
    users = ti.xcom_pull(task_ids = ['users_treatment'])[0]

    users = json.loads(users)
    print('Users after load:', users)
    df = json_normalize(users)
    print('Users dataframe', df)

    df.to_csv('/tmp/data_patients.csv')

with DAG('get_patients', schedule_interval = '@daily', default_args = default_args, 
         catchup = False) as dag:
    
    get_users = PythonOperator(task_id = 'get_users', python_callable = _get_users)

    users_treatment = PythonOperator(task_id = 'users_treatment', python_callable = _users_treatment)

    write_users = PythonOperator(task_id = 'write_users', python_callable = _write_users)

    get_users >> users_treatment >> write_users
