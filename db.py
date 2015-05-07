#!/usr/bin/python
# -*- coding: utf-8 -*-
# #  FileName    : db.py
# #  Author      : ShuYu Wang <andelf@gmail.com>
# #  Created     : Mon May  4 21:35:06 2015 by ShuYu Wang
# #  Copyright   : Feather Workshop (c) 2015
# #  Description : description
# #  Time-stamp: <2015-05-07 10:33:01 andelf>


import os
from peewee import *
import datetime


__dir__ = os.path.dirname(__file__)


db = SqliteDatabase(os.path.join(__dir__, "account.db"), threadlocals=True)

class BaseModel(Model):
    class Meta:
        database = db

    @classmethod
    def has_one(cls, *args, **kwwags):
        try:
            cls.get(*args, **kwwags)
            return True
        except:
            return False


class Account(BaseModel):
    email = CharField(unique=True)
    password = CharField()
    created_at = DateTimeField(default=datetime.datetime.now)
    is_active = BooleanField(default=True)
    memo = CharField(null=True)


    def finish_routine_work(self, started_at, memo=""):
        RoutineWork.create(account = self, started_at, memo=memo)


class RoutineWork(BaseModel):
    account = ForeignKeyField(Account, related_name='routine_works')
    date = DateField(default=datetime.date.today) # should be same as end
    started_at = DateTimeField(default=datetime.datetime.now)
    ended_at = DateTimeField(default=datetime.datetime.now, null=True)

    memo = CharField(null=True)



def create():
    db.connect()
    db.create_tables([Account, RoutineWork], safe=True)

def initdb():
    import csv
    db.connect()

    with open("./account.csv") as fp:
        r = csv.reader(fp)
        for email, password in r:
            Account.create(email=email, password = password)

if __name__ == '__main__':
    create()
    #initdb()
