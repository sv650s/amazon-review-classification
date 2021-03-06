#!/usr/bin/env python
# coding: utf-8


import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from datetime import datetime
import logging
import traceback2
import sys
from util.time_util import TimedReport, TIME_FORMAT, DATE_FORMAT
from util.constants import Keys, Status
from sklearn.externals import joblib
from sklearn.model_selection import train_test_split
import json

# set up logger
log = logging.getLogger(__name__)
MODEL_DIR = "../models"
RSTATE=1


def create_training_data(data: pd.DataFrame, class_column: str, drop_columns: str = None):
    """
    Make a copy of dataframe and:
    1. split between features and predictions
    2. drop any extra columns
    3. create test and training sets
    :param data: dataframe with data to split
    :param class_column: use this column as labels for training
    :param drop_columns: specify a comma delimited list of strings here if there are any extra columns to be dropped (optional)
    :return: X_train, X_test, y_train, y_test
    """
    # make a copy so we can reuse original DF if need be
    x = data.copy()

    y = x[class_column]
    x.drop(class_column, axis=1, inplace=True)

    if drop_columns:
        drop_list = drop_columns.replace(" ", "").split(",")
        log.info(f"Dropping columns from features {drop_list}")
        x.drop(drop_list, axis=1, inplace=True)

    log.info(f'shape of x: {x.shape}')
    log.info(f'shape of y: {y.shape}')

    return train_test_split(x, y, random_state=RSTATE, stratify=y)

class Model(object):
    """
    Encapsulates a model that we will be running
    """

    def __init__(self,
                 model: str,
                 x_train: pd.DataFrame,
                 y_train: pd.DataFrame,
                 x_test: pd.DataFrame,
                 y_test: pd.DataFrame,
                 class_column: str,
                 name: str = None,
                 description: str = None,
                 file: str = None,
                 parameters: dict = None,
                 ):
        """
        :param model:
        :param x_train:
        :param y_train:
        :param x_test:
        :param y_test:
        :param name:
        :param description:
        :param file:
        :param parameters:
        """
        self.model = model
        self.x_train = x_train
        self.y_train = y_train
        self.x_test = x_test
        self.y_test = y_test
        self.class_column = class_column
        self.file = file
        self.parameters = parameters
        self.status = Status.NEW
        self.y_predict = None
        self.status_date = None
        self.message = None

        self.report = TimedReport()
        # if report and isinstance(report, TimedReport):
        #     # outside program may have certain things already timed and recorded, we are going to merge them here
        #     self.report.merge_reports(report)
        # elif report:
        #     raise Exception("report is not a TimedReport")

        if name:
            self.name = name
        else:
            self.name = type(model).__name__
        self.description = f'{description}-{name}-{class_column}'

        train_row, train_col = self.x_train.shape
        test_row, test_col = self.x_test.shape

        rdict = {
            Keys.MODEL_NAME: self.name,
            Keys.DESCRIPTION: self.description,
            Keys.FILE: self.file,
            Keys.TRAIN_EXAMPLES: train_row,
            Keys.TRAIN_FEATURES: train_col,
            Keys.TEST_EXAMPLES: test_row,
            Keys.TEST_FEATURES: test_col,
            Keys.PARAMETERS: json.dumps(parameters)
        }
        self.report.add_dict(rdict)
        # do this here so ti doesn't get flattened

    def run(self, fit: bool = True, report: bool = True):
        """
        Fit and predict model
        :param train: call fit function on model. Set to false when using pre-trained/CV models. Default is True
        :return: report dictionary, y_predict
        """
        log.info('#' * 20)
        log.info(f'Running model: {str(self)}')
        log.info('#' * 20)

        try:

            if fit:
                self.report.start_timer(Keys.TRAIN_TIME_MIN)
                self.model = self.model.fit(self.x_train, self.y_train)
                self.report.end_timer(Keys.TRAIN_TIME_MIN)

            # TODO: add logic for CV's
            model_filename = f'{MODEL_DIR}/{self.description}.jbl'
            self.report.record(Keys.MODEL_FILE, model_filename)
            self.report.start_timer(Keys.MODEL_SAVE_TIME_MIN)
            with open(model_filename, 'wb') as file:
                joblib.dump(self.model, model_filename)
            self.report.end_timer(Keys.MODEL_SAVE_TIME_MIN)

            self.report.start_timer(Keys.PREDICT_TIME_MIN)
            self.y_predict = self.model.predict(self.x_test)
            self.report.end_timer(Keys.PREDICT_TIME_MIN)

            self.report.record(Keys.STATUS, Status.SUCCESS)

        except Exception as e:
            traceback2.print_exc(file=sys.stdout)
            log.error(str(e))
            self.report.record(Keys.STATUS, Status.FAILED)
            self.report.record(Keys.MESSAGE, str(e))
        finally:
            self.report.record(Keys.STATUS_DATE, datetime.now().strftime(TIME_FORMAT))
            log.info(f'Finished running model: {str(self)}')

        # TODO: refactor old notebooks and swith ordering
        if report:
            return self.get_report_dict(), self.y_predict
        return self.y_predict

    def __str__(self):
        """
        Override str method to summarize model
        :return:
        """
        return f'name: {self.name}\n' \
            f'\twith file: {self.file}\n' \
            f'\twith description: {self.description}\n' \
            f'\twith parameters: {self.parameters}\n' \
            f'\tstatus: {self.status}'

    def get_report_dict(self) -> dict:
        """
        Creates a 1 level dictionary that summarizes this model so we can add it to DF later
        :return:
        """
        self.get_classification_report()
        self.get_confusion_matrix()
        # TODO: this is not working - calculate roc_auc
        # roc_auc, fpr, tpr = calculate_roc_auc(self.y_test, self.y_predict)
        # self.report.record(Keys.ROC_AUD, roc_auc)
        return self.report.get_report_dict()

    def get_classification_report(self):
        """
        classification_report returns something like this:
            {'label 1': {'precision':0.5,
                 'recall':1.0,
                 'f1-score':0.67,
                 'support':1},
             'label 2': { ... },
              ...
            }

        This function will take the results and flatten it into one level so we can write it to a DF
        :return:
        """
        log.debug(f'y_predict {self.y_predict}')
        log.debug(f'y_test {self.y_test}')
        if len(self.y_predict) > 0 and len(self.y_test) > 0:
            log.debug(f'getting classificaiton report for {self}')
            c_report = classification_report(self.y_test, self.y_predict, output_dict=True)
            self.report.add_and_flatten_dict(c_report)

    def get_confusion_matrix(self):
        """
        Get confustion matrix and store in report in json format
        :return:
        """
        if len(self.y_predict) > 0 and len(self.y_test) > 0:
            log.debug(f'getting confusion matrix for {self}')
            cm = json.dumps(confusion_matrix(self.y_test, self.y_predict).tolist())
            self.report.record(Keys.CM, cm)


