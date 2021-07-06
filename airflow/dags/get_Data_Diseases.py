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

def _get_diseases():
    # Open Postgres Connection
    with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
        with closing(conn.cursor()) as cursor:
            sql = '''SELECT json_agg(result) FROM (SELECT d.name AS Name_disease, count(*) AS Number_Pacients 
                    FROM patient_disease AS pd
                    LEFT JOIN disease AS d ON d.id = pd.disease_id 
                    LEFT JOIN patient AS p ON pd.patient_id = p.id 
                    GROUP BY d.id) AS result;'''
 
            # Executes the sql
            cursor.execute(sql)
            # Fetch all the data from the executed request
            sources = cursor.fetchall()
            #sources = str(sources[0]).replace('RealDictRow', '')[15:][:-3]
            print(sources)

        return str(sources)

def _diseases_treatment(ti):
    users = ti.xcom_pull(task_ids = ['get_diseases'])

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

def _write_diseases(*op_args, ti):
    users = ti.xcom_pull(task_ids = ['diseases_treatment'])[0]

    users = json.loads(users)
    print('Users after load:', users)
    df = json_normalize(users)
    print('Users dataframe', df)

    df.to_csv('/tmp/data_patients.csv', index = False)

with DAG('get_diseases', schedule_interval = '@daily', default_args = default_args, 
         catchup = False) as dag:
    
    get_diseases = PythonOperator(task_id = 'get_diseases', python_callable = _get_diseases)

    diseases_treatment = PythonOperator(task_id = 'diseases_treatment', python_callable = _diseases_treatment)

    write_diseases = PythonOperator(task_id = 'write_diseases', python_callable = _write_diseases)

    get_diseases >> diseases_treatment >> write_diseases
