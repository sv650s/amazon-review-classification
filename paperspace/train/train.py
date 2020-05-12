
# Commented out IPython magic to ensure Python compatibility.
from __future__ import absolute_import, division, print_function, unicode_literals


import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Activation, Dropout
from tensorflow.keras.layers import BatchNormalization
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.models import load_model
from tensorflow.keras.optimizers import SGD, Adam
from tensorflow.keras.layers import Conv1D, MaxPooling1D, Embedding, \
    SpatialDropout1D, Flatten, LSTM
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing import sequence
from tensorflow.keras.utils import model_to_dot
from tensorflow.keras.initializers import Constant
from tensorflow.keras.models import load_model


from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.utils.class_weight import compute_class_weight

from psutil import virtual_memory

import pandas as pd
import numpy as np
from datetime import datetime
import os
import logging
import argparse


import util.keras_util as ku
import util.report_util as ru

import random

DATE_FORMAT = '%Y-%m-%d'
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# length of our embedding - 300 is standard
EMBED_SIZE = 300

# From EDA, we know that 90% of review bodies have 100 words or less,
# we will use this as our sequence length
MAX_SEQUENCE_LENGTH = 100


# used to fix seeds
RANDOM_SEED = 1


# set up logging
LOG_FORMAT = "%(asctime)-15s %(levelname)-7s %(name)s.%(funcName)s" \
    " [%(lineno)d] - %(message)s"
logger = logging.getLogger(__name__)


def check_resources():
    """
    Check what kind of resources we have for training
    :return:
    """

    # checl to make sure we are using GPU here
    tf.test.gpu_device_name()

    # check that we are using high RAM runtime
    ram_gb = virtual_memory().total / 1e9
    logger.info('Your runtime has {:.1f} gigabytes of available RAM\n'.format(ram_gb))

    # if ram_gb < 20:
    #   print('To enable a high-RAM runtime, select the Runtime → "Change runtime type"')
    #   print('menu, and then select High-RAM in the Runtime shape dropdown. Then, ')
    #   print('re-execute this cell.')
    # else:
    #   print('You are using a high-RAM runtime!')


def fix_seed(seed: int):
    logger.info(f"Fixing rando seed to {seed}")

    # fix random seeds
    tf.compat.v1.reset_default_graph()
    tf.compat.v1.set_random_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

def load_data(data_file: str, feature_column:str, label_column: str):
    """
    Loads data file
    OHE labelcolumn
    split features and labels into train and test set

    :param data_file:
    :param feature_column:
    :param label_column:
    :return:
    """
    logger.info(f'Reading data file: {data_file} feature_column: {feature_column} label_column: {label_column}')

    df = pd.read_csv(data_file)

    # drop any rows with empty feature columns that we may have missed
    logger.info("Dropping rows with empty features...")
    df.dropna(subset = [feature_column, label_column], inplace = True)

    reviews = df[feature_column]
    ratings = df[label_column]

    # pre-process our lables
    # one hot encode our star ratings since Keras/TF requires this for the labels
    y = OneHotEncoder().fit_transform(ratings.values.reshape(len(ratings), 1)).toarray()


    # split our data into train and test sets
    reviews_train, reviews_test, y_train, y_test = train_test_split(reviews, y, random_state=1)

    logger.debug(f'features dimensions - train {np.shape(reviews_train)} test {np.shape(reviews_test)}')
    logger.debug(f'label dimensions - train {np.shape(y_train)} test {np.shape(y_test)}')

    return reviews_train, reviews_test, y_train, y_test, ratings

def preprocess_data(feature_train, feature_test, embedding_file: str, missing_words_file: str):
    """
    Tokenize text and convert features into embedding matrix

    Pre-trained embedding will be converted into an index file in the same directory as embedding file
    This index file will be loaded instead of the embedding file to save time

    :param feature_train: training feature set
    :param feature_test: test feature set
    :param embedding_file: full path name of pre-trained embedding file
    :param missing_words_file: full path name to store missing words csv file
    :return:
        X_train, X_test, t, embedding_matrix
    """
    logger.info(f'feature train dimensions {np.shape(feature_train)} feature test dimensions {np.shape(feature_test)}')

    logger.info("Tokenizing features...")
    # Pre-process our features (review body)
    t = Tokenizer(oov_token="<UNK>")
    # fit the tokenizer on the documents
    t.fit_on_texts(feature_train)
    # tokenize both our training and test data
    train_sequences = t.texts_to_sequences(feature_train)
    test_sequences = t.texts_to_sequences(feature_test)

    logger.info("Vocabulary size={}".format(len(t.word_counts)))
    logger.info("Number of Documents={}".format(t.document_count))


    # pad our reviews to the max sequence length
    X_train = sequence.pad_sequences(train_sequences, maxlen=MAX_SEQUENCE_LENGTH)
    X_test = sequence.pad_sequences(test_sequences, maxlen=MAX_SEQUENCE_LENGTH)

    logger.info(f'Train review vectors shape: {np.shape(X_train)} Test review vectors shape: {np.shape(X_test)}')

    """## Load our pre-trained embedding

    embedding_index will be a map where key == word, value == the embedding vector
    """

    embedding_dir = os.path.dirname(embedding_file)
    embedding_index_file = f'{embedding_dir}/glove.840B.300d-embedding_index'

    embedding_index = {}

    logger.info("Creating embedding index...")
    if os.path.exists(f'{embedding_index_file}.npy'):
      logger.info(f'Loading {embedding_index_file}.npy')
      embedding_index = np.load(f'{embedding_index_file}.npy',
                                 allow_pickle = True).item()
    else:
      logger.info(f'{embedding_index_file} does not exist. Indexing words from {embedding_file}...')

      with open(embedding_file) as f:
          for line in f:
              word, coefs = line.split(maxsplit=1)
              coefs = np.fromstring(coefs, 'f', sep=' ')
              embedding_index[word] = coefs
      logger.info(f'Saving embedding index to {embedding_index_file}...')
      np.save(embedding_index_file, embedding_index)

    logger.debug(f'embedding_index type {type(embedding_index)} shape {np.shape(embedding_index)}')
    logger.info('Found %s word vectors.' % len(embedding_index))



    """## Create Embedding Matrix based on our tokenizer

    For every word in our vocabulary, we will look up the embedding vector and add the it to our embedding matrix

    The matrix will be passed in as weights in our embedding layer later

    If there is word that does not exist in the pre-trained embedding vocabulary, we will leave the weights as 0 vector and save off the word into a CSV file later for analysis
    """

    # this is a map with key == word, value == index in the vocabulary
    word_index = t.word_index
    logger.info(f'word_index length: {len(word_index)}')

    # start with a matrix of 0's
    embedding_matrix = np.zeros((len(word_index) + 1, EMBED_SIZE))
    logger.debug(f'embedding_matrix shape: {np.shape(embedding_matrix)}')

    # if a word doesn't exist in our vocabulary, let's save it off
    logger.info("Creating embedding matrix from embedding index...")
    missing_words = []
    for word, i in word_index.items():
        # logger.info(f'word: {word} i: {i}')
        embedding_vector = embedding_index.get(word)
        if embedding_vector is not None and np.shape(embedding_vector)[0] == EMBED_SIZE:
            # words not found in embedding index will be all-zeros.
            # logger.info(f'i: {i} embedding_vector shape: {np.shape(embedding_vector)}')
            embedding_matrix[i] = embedding_vector
        else:
          missing_words.append(word)

    logger.info(f'Number of missing words from our vocabulary: {len(missing_words)}')

    """Save off our missing words into a csv file so we can analyze this later"""

    # save missing words into a file so we can analyze it later
    missing_words_df = pd.DataFrame(missing_words)
    logger.info("Saving missing words file...")
    missing_words_df.to_csv(missing_words_file, index=False)

    return X_train, X_test, t, embedding_matrix



if __name__ == "__main__":

    start_time = datetime.now()

    check_resources()
    fix_seed(RANDOM_SEED)

    parser = argparse.ArgumentParser()

    parser.add_argument("-i", "--input_dir", help="input directory. Default /storage/data",
                        default="/storage/data")
    parser.add_argument("-o", "--output_dir", help="output directory. Default /artifacts",
                        default="/artifacts")


    parser.add_argument("-d", "--dropout_rate", help="dropout rate. Default 0",
                        default=0)
    parser.add_argument("-r", "--recurrent_dropout_rate", help="recurrent dropout rate. NOTE: will not be able to " \
            "cuDNN if this is set. Default 0",
                        default=0)
    parser.add_argument("-f", "--feature_column", help="feature column. Default review_body",
                        default="review_body")
    parser.add_argument("-t", "--truth_label_column", help="label column. Default star_rating",
                        default="star_rating")

    parser.add_argument("-m", "--train_embeddings",
                        help="set this flag to make enbedding layer trainable. Default False",
                        default=False,
                        action="store_true")
    parser.add_argument("-n", "--bidirectional",
                        help="label column. Default star_rating",
                        default=False,
                        action="store_true")
    parser.add_argument("-u", "--unbalanced_class_weights",
                        help="do not balance class weights for training",
                        default=False,
                        action="store_true")

    parser.add_argument("-p", "--patience", help="patience. Default = 4", default=4)
    parser.add_argument("-c", "--lstm_cells", help="Number of LSTM cells. Default = 128", default=128)
    parser.add_argument("-a", "--learning_rate", help="Optimizer learning rate. Default = 0.001", default=0.001)
    parser.add_argument("-e", "--epochs", help="Max number epochs. Default = 20", default=20)
    parser.add_argument("-b", "--batch_size", help="Training batch size. Default = 32", default=32)
    parser.add_argument("-v", "--model_version", help="Specify model version. Default = 1", default=1)

    parser.add_argument("-l", "--loglevel", help="log level", default="INFO")

    # POSITIONAL ARGUMENTS
    parser.add_argument("sample_size",
                        help="Sample size (ie, 50k, test)",
                        type=str)

    # get command line arguments
    args = parser.parse_args()

    # process argument
    if args.loglevel is not None:
        loglevel = getattr(logging, args.loglevel.upper(), None)
    logging.basicConfig(format=LOG_FORMAT, level=loglevel)
    logger = logging.getLogger(__name__)






    input_dir = args.input_dir
    output_dir = args.output_dir
    label_column = args.truth_label_column
    feature_column = args.feature_column
    sample_size = args.sample_size

    lstm_cells = int(args.lstm_cells)
    epochs  = int(args.epochs)
    batch_size = int(args.batch_size)
    patience = int(args.patience)
    learning_rate = float(args.learning_rate)
    model_version = int(args.model_version)

    dropout_rate = float(args.dropout_rate)
    recurrent_dropout_rate = float(args.recurrent_dropout_rate)

    bidirectional = args.bidirectional
    balance_class_weights = not args.unbalanced_class_weights
    train_embeddings = args.train_embeddings


    data_dir = f'{input_dir}/amazon_reviews'
    embeddings_dir = f'{input_dir}/embeddings'
    reports_dir = f'{output_dir}/reports'
    models_dir = f'{output_dir}/models'

    debug = False
    if sample_size == "test":
        logger.info("Running in DEBUG mode")
        debug = True

    # process argument
    if debug:
        loglevel = logging.DEBUG
        # override parameters to make testing faster
        epochs = 1
        lstm_cells = 16
    elif args.loglevel is not None:
        loglevel = getattr(logging, args.loglevel.upper(), None)
    logging.basicConfig(format=LOG_FORMAT, level=loglevel)
    logger = logging.getLogger(__name__)

    if bidirectional:
        bidirectional_name = "bi"
    else:
        bidirectional_name = ""

    if balance_class_weights:
        balanced_name = "B"
    else:
        balanced_name = ""

    model_name = f"{bidirectional_name}LSTM{balanced_name}{lstm_cells}"
    DESCRIPTION = f"1 Layer {lstm_cells} {model_name} Units, Dropout {dropout_rate}, Recurrent Dropout {recurrent_dropout_rate}, Batch Size {batch_size}, Learning Rate {learning_rate}"
    architecture = f"1x{lstm_cells}"
    FEATURE_SET_NAME = "glove_with_stop_nonlemmatized"
    # TODO: add in sampling options


    REPORT_FILE = f"paperspace-{model_name}-" \
        f"{architecture}-" \
        f"dr{ku.get_decimal_str(dropout_rate)}-" \
        f"rdr{ku.get_decimal_str(recurrent_dropout_rate)}-" \
        f"batch{batch_size}-" \
        f"lr{ku.get_decimal_str(learning_rate)}-" \
        f"{FEATURE_SET_NAME}-" \
        f"sampling_none-" \
        f"{feature_column}-" \
            "report.csv"

    if debug:
      data_file = f'{data_dir}/amazon_reviews_us_Wireless_v1_00-test-with_stop_nonlemmatized-preprocessed.csv'
      model_name = f'test-{model_name}'
      MISSING_WORDS_FILE = f'{reports_dir}/glove_embedding-missing_words-test.csv'
      ku.ModelWrapper.set_report_filename(f'test-{REPORT_FILE}')
    else:
      data_file = f"{data_dir}/amazon_reviews_us_Wireless_v1_00-{sample_size}-with_stop_nonlemmatized-preprocessed.csv"
      MISSING_WORDS_FILE = f'{reports_dir}/glove_embedding-missing_words-{sample_size}.csv'
      ku.ModelWrapper.set_report_filename(REPORT_FILE)


    EMBEDDING_FILE = f'{embeddings_dir}/glove.840B.300d.txt'


    # summary = f'\nParameters:\n' \
    #           f'\tinput_dir:\t\t\t{input_dir}\n' \
    #           f'\toutput_dir:\t\t\t{output_dir}\n' \
    #           f'\tdata_file:\t\t\t{data_file}\n' \
    #           f'\tlabel_column:\t\t\t{label_column}\n' \
    #           f'\tfeature_column:\t\t\t{feature_column}\n' \
    #           f'\tsample_size:\t\t\t{sample_size}\n' \
    #           f'\nEmbedding Info:\n' \
    #           f'\tFEATURE_SET_NAME:\t\t{FEATURE_SET_NAME}\n' \
    #           f'\tEMBED_SIZE:\t\t\t{EMBED_SIZE}\n' \
    #           f'\tMAX_SEQUENCE_LENGTH:\t\t{MAX_SEQUENCE_LENGTH}\n' \
    #           f'\tEMBEDDING_FILE:\t\t\t{EMBEDDING_FILE}\n' \
    #           f'\ttrain_embeddings:\t\t{train_embeddings}\n' \
    #           f'\nModel Info:\n' \
    #           f'\tmodel_name:\t\t\t{model_name}\n' \
    #           f'\tlstm_cells:\t\t\t{lstm_cells}\n' \
    #           f'\tlearning_rate:\t\t\t{learning_rate}\n' \
    #           f'\tpatience:\t\t\t{patience}\n' \
    #           f'\tepochs:\t\t\t\t{epochs}\n' \
    #           f'\tbatch_size:\t\t\t{batch_size}\n' \
    #           f'\tdropout_rate:\t\t\t{dropout_rate}\n' \
    #           f'\trecurrent_dropout_rate:\t\t{recurrent_dropout_rate}\n'
    # logger.info(summary)



    ##### validate that we have the correct directories before we start
    if os.path.exists(input_dir):
        if not os.path.exists(f'{embeddings_dir}'):
            os.mkdir(f'{embeddings_dir}')
    else:
        logger.error(f'ERROR: {input_dir} does not exist')
        exit(1)

    if os.path.exists(output_dir):
        if not os.path.exists(f'{reports_dir}'):
            logger.info(f'{reports_dir} missing. Creating...')
            os.mkdir(f'{reports_dir}')
        if not os.path.exists(f'{models_dir}'):
            logger.info(f'{models_dir} missing. Creating...')
            os.mkdir(f'{models_dir}')
    else:
        logger.error(f'ERROR: {output_dir} does not exist')
        exit(1)


    reviews_train, reviews_test, y_train, y_test, ratings = load_data(data_file, feature_column, label_column)

    X_train, X_test, t, embedding_matrix = preprocess_data(reviews_train,
                                                           reviews_test,
                                                           EMBEDDING_FILE,
                                                           MISSING_WORDS_FILE)

    vocab_size = len(t.word_index)+1

    reduce_lr = ReduceLROnPlateau(monitor='val_loss',
                                  restore_best_weights=True)

    early_stop = EarlyStopping(monitor='val_loss',
                               patience=patience,
                               verbose=1,
                               restore_best_weights=True)

    logger.debug(f'y_train: {y_train[:5]} ratings {ratings[:5]}')
    weights = compute_class_weight('balanced', np.arange(1, 6), ratings)
    weights_dict = {i: weights[i] for i in np.arange(0, len(weights))}
    logger.info(f'class weights: {weights}')
    logger.info(f'class weights_dict: {weights_dict}')



    mw = ku.LSTM1LayerModelWrapper(
                            lstm_dim = lstm_cells, # LSTM dim - LSTM1LyerModelWrapper
                             dropout_rate = dropout_rate, # dropout rate - LSTM1LyerModelWrapper
                             recurrent_dropout_rate = recurrent_dropout_rate, # recurrent dropout rate - LSTM1LyerModelWrapper
                             bidirectional = bidirectional, # bidirectional - LSTM1LyerModelWrapper
                             vocab_size = vocab_size,       # vocab size - EmbeddingModelWrapper
                             max_sequence_length = MAX_SEQUENCE_LENGTH, # max sequence length - EmbeddingModelWrapper
                             embed_size = EMBED_SIZE, # embed size - EmbeddingModelWrapper
                            train_embeddings  =  train_embeddings, # trainable embedding - EmbeddingModelWrapper
                            model_name = model_name, # model name - ModelWrapper
                            architecture = architecture, # architecture - ModelWrapper
                            feature_set_name = FEATURE_SET_NAME, # feature_set_name - ModelWrapper
                            label_column = label_column, # label_column - ModelWrapper
                            feature_column = feature_column, # feature_column - ModelWrapper
                            data_file = data_file, # data file - ModelWrapper
                            sample_size_str = sample_size, # sample size
                            tokenizer = t, # tokenizer - ModelWrapper
                            description = DESCRIPTION, #description - ModelWrapper
                            optimizer_name = "Adam", # string optimizer name
                            learning_rate = learning_rate, # learning rate - ModelWrapper
                            model_version= model_version, # model version - ModelWrapper
                            save_dir = output_dir # where to save outputs - ModelWrapper
    )

    mw.add("environment", "paperspace")
    mw.add("patience", patience)


    network_history = mw.fit(X_train,
                             y_train,
                             batch_size=batch_size,
                             epochs=epochs,
                             verbose=1,
                             validation_split=0.2,
                             balance_class_weights=balance_class_weights,
                             callbacks=[early_stop, reduce_lr])

    mw.evaluate(X_test, y_test)
    logger.info("Train Accuracy: %.2f%%" % (mw.train_scores[1]*100))
    logger.info("Test Accuracy: %.2f%%" % (mw.test_scores[1]*100))

    # pu.plot_network_history(mw.network_history, "categorical_accuracy", "val_categorical_accuracy")
    # plt.show()

    logger.info("\nConfusion Matrix")
    logger.info(mw.test_confusion_matrix)
    
    logger.info("\nClassification Report")
    logger.info(mw.test_classification_report)

    # fig = plt.figure(figsize=(5,5))
    # pu.plot_roc_auc(mw.model_name, mw.roc_auc, mw.fpr, mw.tpr)

    custom_score = ru.calculate_metric(mw.test_crd)
    logger.info(f'Custom Score: {custom_score}')

    """**Save off various files**"""

    mw.save(append_report=True)

    """# Test That Our Models Saved Correctly"""

    logger.info("Reloading model for testing...")
    model_loaded = load_model(mw.model_file)
    scores = model_loaded.evaluate(X_test, y_test, verbose=1)
    accuracy = scores[1] * 100
    logger.info("Accuracy: %.2f%%" % (accuracy))

    # this takes too long for real models
    if debug == True:
      y_predict = model_loaded.predict(X_test)
      y_predict_unencoded = ku.unencode(y_predict)
      y_test_unencoded = ku.unencode(y_test)

      # classification report
      logger.info(classification_report(y_test_unencoded, y_predict_unencoded))

      # confusion matrix
      logger.info(confusion_matrix(y_test_unencoded, y_predict_unencoded))

    end_time = datetime.now()
    logger.info(f'Finished training {mw}')
    logger.info("Accuracy: %.2f%%" % (accuracy))
    logger.info("Custom Score: %.2f%%" % (custom_score))
    logger.info(f'Star Time: {start_time}')
    logger.info(f'End Time: {end_time}')
    logger.info(f'Total Duration: {round((end_time - start_time).total_seconds() / 60, 2)} mins')
