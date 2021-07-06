from airflow.models import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.postgres_hook import PostgresHook
from airflow.utils.task_group import TaskGroup

from datetime import datetime
from pandas import read_json, read_sql_query
from contextlib import closing

default_args = {
    'start_date': datetime(2021, 7, 1, 16, 29) # Minus 1 hour for the airflow timezone to match ours
}

# COUNTRIES ---------------------------------------------------------------
def _get_countries(ti):
    # Open Postgres Connection
    with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
        sql = '''SELECT * FROM countries_plus_country;'''
 
        df = read_sql_query(sql, con = conn)
        df = df.drop(columns = ['iso3', 'iso_numeric', 'fips', 'tld', 'currency_symbol', 'postal_code_format', 
                                'postal_code_regex', 'geonameid', 'equivalent_fips_code'])

        ti.xcom_push(key = 'get_data', value = df.to_json())

# DISEASES ---------------------------------------------------------------
def _get_diseases(ti):
    # Open Postgres Connection
    with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
        sql = '''SELECT d.name AS "Name of Disease", count(*) AS "Number of Pacients" 
                    FROM patient_disease AS pd
                    LEFT JOIN disease AS d ON d.id = pd.disease_id 
                    LEFT JOIN patient AS p ON pd.patient_id = p.id 
                    GROUP BY d.id;'''
 
        df = read_sql_query(sql, con = conn)

        ti.xcom_push(key = 'get_data', value = df.to_json())

# CATARACT BY SEX ---------------------------------------------------------------
def _get_cataract_sex(ti):
    # Open Postgres Connection
    with closing(PostgresHook(postgres_conn_id = 'postgres_default').get_conn()) as conn:
        sql = '''SELECT fem as "Cataract Females", mas as "Cataract Males" FROM (
            SELECT count(p.sex) FROM patient_disease AS pd
                LEFT JOIN disease AS d ON d.id = pd.disease_id 
                LEFT JOIN patient AS p ON pd.patient_id = p.id 
                WHERE p.sex = 'F' AND d.name = 'Cataract') as fem,
            (
            SELECT count(p.sex) FROM patient_disease AS pd
                LEFT JOIN disease AS d ON d.id = pd.disease_id 
                LEFT JOIN patient AS p ON pd.patient_id = p.id
                 WHERE p.sex = 'M' AND d.name = 'Cataract') as mas;'''
 
        df = read_sql_query(sql, con = conn)

        ti.xcom_push(key = 'get_data', value = df.to_json())


def _store_data(ti):
    data = ti.xcom_pull(key = 'get_data',
                        task_ids = ['get_cataract_sex', 
                                    'get_diseases', 
                                    'get_countries'])

    file_names = ['/tmp/data_cataracts_sex.csv', 
                  '/tmp/data_diseases.csv', 
                  '/tmp/data_countries.csv']

    for i in range(len(data)):
        print(data[i])
        d = read_json(data[i])

        d.to_csv(file_names[i], index = False)

    
# DAG ---------------------------------------------------------------
with DAG('get_as_dataframe_otimized', schedule_interval = '@daily', default_args = default_args, 
         catchup = False) as dag:
    get_diseases = PythonOperator(task_id = 'get_diseases', python_callable = _get_diseases)

    get_cataract_sex = PythonOperator(task_id = 'get_cataract_sex', python_callable = _get_cataract_sex)

    get_countries = PythonOperator(task_id = 'get_countries', python_callable = _get_countries)

    store_data = PythonOperator(task_id = 'store_data', python_callable = _store_data)

    [get_diseases, get_cataract_sex, get_countries] >> store_data

