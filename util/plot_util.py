import matplotlib.pyplot as plt
import seaborn as sns
import re
import pandas as pd
from tensorflow.keras.models import load_model
import numpy as np
import logging
import json
import util.dict_util as du

log = logging.getLogger(__name__)


# common utilities for various notebooks


# function to print mutltiple histograms
def plot_score_histograms(df: pd.DataFrame, version = 1, **kwargs):
    """
    Wrapper function to call different versions of plot_score_historgrams

    I did this so previous notebooks would not break. Version is default to 1
    :param df: data to plot
    :param version: version of the plotting function to call. Default is version 1
    :param kwargs: arguments for the plotting function. Only used for version 2. Supported params: label, groupby
    :return:
    """
    if version == 1:
        _plot_score_histograms_v1(df)
    elif version == 2:
        _plot_score_histograms_v2(df, kwargs)
    else:
        raise Exception(f"version {version} not supported")


def _plot_score_histograms_v1(df: pd.DataFrame):
    """
    Plot F1, precision and recall for various models

    Use this for notebooks before 11/2019
    :param df: 
    :return: 
    """
    if "label" not in df.columns:
        df["label"] = df.apply(lambda x: f'{x["model_name"]}-{x["description"]}', axis=1)

    models = df["model_name"].unique()
    f1_cols, precision_cols, recall_cols = get_score_columns(df)
    for model in models:
        model_report = df[df["label"].str.startswith(f'{model}-')]

        pos = list(range(len(model_report)))
        width = 0.15
        f, a = plt.subplots(1, 3, sharex=True, sharey=True, figsize=(20, len(model_report) * 1))
        column_dict = {"F1": f1_cols, "Precision": precision_cols, "Recall": recall_cols}

        # sort the report in reverse order so we see the models top down
        report_reverse = model_report.sort_values("label", ascending=False)

        index = 0
        for title, columns in column_dict.items():
            columns_copy = columns.copy()
            columns_copy.remove("label")
            # sort in reverse order so it goes top-down and 5 is at the bottom
            columns_copy.sort(reverse=True)

            offset = 0
            for col in columns_copy:
                #         print(f'Plotting {col}')
                a[index].barh([p + offset for p in pos],
                              report_reverse[col],
                              width,
                              #                 align="edge",
                              #                 alpha=0.5,
                              tick_label=report_reverse["label"].tolist(),
                              orientation="horizontal")
                offset += width
                a[index].set_title(title)
                a[index].set_xlim(0, 1.0)
            index += 1

def _plot_score_histograms_v2(df: pd.DataFrame, args, **kwargs):
    """
    You should not call this function directly but use plot_score_historgrams and specify version = 2

    Use this to plot F1 score, precision and recall for notebooks after 11/19 where classification report is stored as json

    By default this will group the graphs by model_name and use feature_summary as the labels for each sub-graph

    You can overwrite this behavior by passing in groupby and label

    :param df:
    :param args: dictionary with arugments - supports: groupby, label, title, training_data
    :return:
    """
    # default values
    label = "feature_summary"
    groupby = None
    title = None
    if args is not None and len(args.keys()) > 0:
        if "label" in args.keys():
            label = args["label"]
        if "groupby" in args.keys():
            groupby = args["groupby"]
        if "title" in args.keys():
            title = args["title"]

    # models = df[[label_column]].unique()
    if groupby is not None:
        log.info(f"Grouping by {groupby}")
        for group in df[groupby].unique():
            model_report = df[df[groupby] == groupby]
            _plot_score_histogram_group(model_report, label = label, group= groupby, title= title)
    else:
        _plot_score_histogram_group(df, label = label, title = title)


def _plot_score_histogram_group(report:pd.DataFrame, label:str, title: str = None, group:str = None, is_training_data = False):
    """
    Plots one grouping of score/histograms
    :param report: model report df
    :param label: column name to use as labels on the left
    :param group: column name to group histograms
    :return:
    """
    f1_cols, precision_cols, recall_cols = get_score_columns(report, is_training_data)

    pos = list(range(len(report)))
    width = 0.15
    f, a = plt.subplots(1, 3, sharex=True, sharey=True, figsize=(20, len(report) * 1))
    if title is not None:
        _ = plt.suptitle(title)
    column_dict = {"F1": f1_cols, "Precision": precision_cols, "Recall": recall_cols}

    # sort the report in reverse order so we see the models top down
    report_reverse = report.sort_values(label, ascending=False)
    # report_reverse = model_report.sort_values("label", ascending=False)

    index = 0
    for title, columns in column_dict.items():
        columns_copy = columns.copy()
        columns_copy.remove("label")
        # sort in reverse order so it goes top-down and 5 is at the bottom
        columns_copy.sort(reverse=True)

        offset = 0
        for col in columns_copy:
            #         print(f'Plotting {col}')
            a[index].barh([p + offset for p in pos],
                          report_reverse[col],
                          width,
                          #                 align="edge",
                          #                 alpha=0.5,
                          tick_label=report_reverse[label].tolist(),
                          # tick_label=report_reverse["label"].tolist(),
                          orientation="horizontal")
            offset += width
            if group is not None:
                a[index].set_title(f'{title}-{group}')
            else:
                a[index].set_title(f'{title}')

            a[index].set_xlim(0, 1.0)
        index += 1


def plot_macro_data(df: pd.DataFrame, cv=False):
    """
    Plots macro f1 score, precision, and recall against timed events for model - ie, training, predict, etc

    :param df:
    :param cv:
    :return:
    """
    if "label" not in df.columns:
        df["label"] = df.apply(lambda x: f'{x["model_name"]}-{x["description"]}', axis=1)

    df = df.sort_values(["label"])

    f, a = plt.subplots(1, 1, figsize=(20, 5))

    g = sns.lineplot(data=df, x="label", y="macro avg_f1-score", label="avg_f1-score", ax=a, color="r")
    g = sns.lineplot(data=df, x="label", y="macro avg_precision", label="avg_precision", ax=a, color="b")
    g = sns.lineplot(data=df, x="label", y="macro avg_recall", label="avg_recall", ax=a, color="g")
    g.set_xticklabels(labels=df["label"], rotation=90)
    g.set_ylabel("percentage")
    g.set_title("Macro Average Scores And Total Time")
    g.legend(loc="upper left")

    ax2 = a.twinx()

    x = df.label.tolist()
    predict_times = df.total_time_min.tolist()
    fit_times = (df.file_load_time_min + df.train_time_min).tolist()
    if cv:
        cv_times = (df.cv_time_min + df.file_load_time_min + df.train_time_min)
    load_times = df.file_load_time_min.tolist()

    g = sns.barplot(data=df, x="label", y="predict_time_min", label="Predict Time", ax=ax2, color="c", alpha=0.5)
    if cv:
        g = sns.barplot(x=x, y=cv_times, label="CV Time", ax=ax2, color="tab:green", alpha=0.5)
    g = sns.barplot(x=x, y=fit_times, label="Fit Time", ax=ax2, color="tab:orange", alpha=0.5)
    g = sns.barplot(x=x, y=load_times, label="File Load Time", ax=ax2, color="tab:blue", alpha=0.5)
    ax2.tick_params(axis='y', labelcolor="c")
    _ = ax2.legend(loc="upper right")


# function that we will use later
def get_score_columns(df: pd.DataFrame, is_training_data = False) -> (list, list, list):
    """
    Gets the different score columns from a results DF
    :param df:
    :return:
    """
    if is_training_data:
        CLASS_F1_COLS = [col for col in df.columns if len(re.findall(r'^(train_\d.+score)', col)) > 0]
    else:
        CLASS_F1_COLS = [col for col in df.columns if len(re.findall(r'^(\d.+score)', col)) > 0]
    CLASS_F1_COLS.append("label")
    #     print(CLASS_F1_COLS)

    if is_training_data:
        CLASS_PRECISION_COLS = [col for col in df.columns if len(re.findall(r'^(train_\d+_precision)', col)) > 0]
    else:
        CLASS_PRECISION_COLS = [col for col in df.columns if len(re.findall(r'^(\d+_precision)', col)) > 0]
    CLASS_PRECISION_COLS.append("label")
    #     print(CLASS_PRECISION_COLS)

    if is_training_data:
        CLASS_RECALL_COLS = [col for col in df.columns if len(re.findall(r'^(train_\d+_recall)', col)) > 0]
    else:
        CLASS_RECALL_COLS = [col for col in df.columns if len(re.findall(r'^(\d+_recall)', col)) > 0]
    CLASS_RECALL_COLS.append("label")
    #     print(CLASS_RECALL_COLS)

    return CLASS_F1_COLS, CLASS_PRECISION_COLS, CLASS_RECALL_COLS


def display_confusion_matrix(row: pd.Series):
    """
    Display confusion matrix 
    :param df: row in report that represents one test run
    :return: 
    """
    matrix = row.confusion_matrix.iloc[0]
    matrix = matrix.replace('\\n', '\n')
    print(matrix)


def display_model_summary(row: pd.Series):
    """
    Loads the model file and print summary of the model
    :param row: row in a report df
    :return:
    """
    print(f"\n\n{row.description}\n")
    model = load_model(row.model_file)
    print(model.summary())


def plot_roc_auc(model_name, roc_auc, fpr, tpr):
    """
    Plots ROC_AUC curve

    :param model_name: name of model - used to label the graph
    :param roc_auc:
    :param fpr:
    :param tpr:
    :return:
    """
    for i in np.arange(0, len(fpr.keys()) - 2):
        plt.plot(fpr[str(i)], tpr[str(i)], label=f'Rating {i + 1}')
    plt.plot(fpr["micro"], tpr["micro"], label="Micro Average ROC",
             linestyle=":", linewidth=4, color='pink')
    plt.plot(fpr["macro"], tpr["macro"], label="Macro Average ROC",
             linestyle=":", linewidth=4, color='black')
    plt.plot([0, 1], [0, 1], color='navy', linestyle='--')

    space = 0
    for i in np.arange(0, len(fpr.keys()) - 2):
        plt.text(x=0, y=-0.25 + space,
                 s=f'Rating {i + 1} AUC: {roc_auc[f"auc_{i + 1}"]}',
                 withdash=True)
        space -= 0.05
    plt.text(x=0, y=-0.25 + space,
             s=f'Micro AUC: {roc_auc["auc_micro"]}',
             withdash=True)
    space -= 0.05
    plt.text(x=0, y=-0.25 + space,
             s=f'Macro AUC: {roc_auc["auc_macro"]}',
             withdash=True)

    plt.legend(loc='lower right')
    plt.xlabel('FPR')
    plt.ylabel('TPR')
    plt.title(f'{model_name} ROC AUC')


def plot_network_history(network_history,
                         accuracy_label:str = "categorical_accuracy",
                         val_accuracy_label:str = "val_categorical_accuracy",
                         description = None,
                         stored_history = False,
                         figsize = (10, 5),
                         title_font_size = 24):
    """
    Plots 2 graphs from network history
    1. epochs vs loss
    2. epochs vs accuracy

    :param network_history: network history object
    :param stored_history: indicates whether network_history object is raw object from model training or if it's from stored object. Default True
    :param accuracy_label: label to cuse for accuracy plot. Default categorical_accuracy
    :param val_accuracy_label: label to cuse for validation accuracy plot. Default val_categorical_accuracy
    :return: None
    """
    f, a = plt.subplots(1, 2, figsize = figsize, sharex = True)

    # print title across subplots
    if description is not None:
        f.suptitle(f"Network History - {description}", fontsize=title_font_size)
    else:
        f.suptitle("Network History", fontsize = title_font_size)

    if isinstance(network_history, dict):
        history = network_history
    else:
        history = network_history.history

    _ = a[0].set_xlabel('Epochs')
    _ = a[0].set_ylabel('Loss')
    _ = plt.legend(['Training', 'Validation'], loc='lower left')
    sns.lineplot(x = np.arange(1, len(history['loss']) + 1), y = history['loss'], ax=a[0], label = "Training", marker = "o")
    sns.lineplot(x = np.arange(1, len(history['val_loss']) + 1), y = history['val_loss'], ax=a[0], label = "Validation", marker = "o")
    # plt.plot(history['loss'], ax=a[0])
    # plt.plot(history['val_loss'], ax=a[0])

    _ = a[1].set_xlabel('Epochs')
    _ = a[1].set_ylabel('Accuracy')
    _ = plt.legend(['Training', 'Validation'], loc='lower left')
    sns.lineplot(x = np.arange(1, len(history[accuracy_label]) + 1), y = history[accuracy_label], ax=a[1], label = "Training", marker = "o")
    sns.lineplot(x = np.arange(1, len(history[val_accuracy_label]) + 1), y = history[val_accuracy_label], ax=a[1], label = "Validation", marker = "o")
    # sns.lineplot(data = history[accuracy_label], ax=a[1])
    # sns.lineplot(data = history[val_accuracy_label], ax=a[1])


    plt.show()

