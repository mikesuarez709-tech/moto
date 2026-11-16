from contextlib import contextmanager

import mysql.connector
from flask import current_app, g


def connection():
    if "motor_db" not in g:
        g.motor_db = mysql.connector.connect(**current_app.config["DATABASE"])
    return g.motor_db


def close_connection(_error=None):
    if db := g.pop("motor_db", None):
        db.close()


@contextmanager
def atomic():
    db = connection()
    db.start_transaction()
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def rows(sql, args=()):
    with connection().cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def row(sql, args=()):
    with connection().cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()


def execute(sql, args=()):
    with connection().cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.lastrowid
