"""Seed only an explicitly named empty synthetic schema; reduce reader grants."""
import argparse
import os
import pymysql
from app.erp_samples import SCHEMA, records


def seed(batch=1):
    database = os.environ.get('PRISM_MYSQL_DATABASE', 'prism_erp')
    if database != 'prism_erp':
        raise ValueError('Seeder is restricted to the prism_erp synthetic database')
    with pymysql.connect(host='127.0.0.1', port=int(os.getenv('PRISM_MYSQL_PORT', '3307')),
                         user='root', password=os.environ['PRISM_MYSQL_ROOT_PASSWORD'], database=database) as db:
        with db.cursor() as cur:
            cur.execute('SHOW TABLES')
            if cur.fetchall():
                raise ValueError('Refusing to overwrite a nonempty database')
            for table, ddl in SCHEMA.items():
                cur.execute(f'CREATE TABLE `{table}` ({ddl}) ENGINE=InnoDB')
            for table, values in records(batch).items():
                cur.executemany(f'INSERT INTO `{table}` VALUES ({",".join("%s" for _ in values[0])})', values)
            cur.execute("REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'prism_reader'@'%'")
            cur.execute("GRANT SELECT ON prism_erp.* TO 'prism_reader'@'%'")
        db.commit()
    print('Synthetic ERP seeded; prism_reader restricted to SELECT.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, choices=range(1, 21), default=1)
    seed(parser.parse_args().batch)
