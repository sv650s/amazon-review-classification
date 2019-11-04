#
#
import sys
sys.path.append('../')


import os
import argparse
import pandas as pd
import logging
from util.TextPreprocessor import TextPreprocessor
import re
import util.file_util as fu
from datetime import datetime


# set up logging
LOG_FORMAT = "%(asctime)-15s %(levelname)-7s %(name)s.%(funcName)s" \
    " [%(lineno)d] - %(message)s"
logger = logging.getLogger(__name__)

STOP_WORDS_TO_REMOVE=[
    'no',
    'not',
    'do',
    'does',
    'did',
    'does',
    'should',
    'very',
    'will'
    ]


def remove_amazon_tags(text: str) -> str:
    """
    removes amazon tags that look like [[VIDEOID:dsfjljs]], [[ASIN:sdjfls]], etc
    :param text:
    :return:
    """
    logger.debug(f"before amazon tags {text}")
    text = re.sub(r'\[\[.*?\]\]', ' ', text, re.I | re.A)
    text = ' '.join(text.split())
    logger.debug(f"after processing amazon tags {text}")
    return text

def remove_http_links(text: str) -> str:
    """
    Amazon reviews sometimes have http tags that link to images. Want to remove these
    :param text:
    :return:
    """
    text = re.sub(r'(http[s]{0,1}:\S+)', '', text, re.I | re.A)
    return text

def expand_star_ratings(text: str) -> str:
    """
    for reviews we may have people writing things like 1 star or
    :param text:
    :return:
    """


def main():
    # set up argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument("datafile", help="source data file")
    parser.add_argument("-o", "--outdir", help="output directory", default="dataset/amazon_reviews")
    parser.add_argument("-l", "--loglevel", help="log level", default="INFO")
    parser.add_argument("-r", "--retain", help="specifieds which columns to keep - NOT YET IMPLEMENTED", action="store_true", default=False)
    parser.add_argument("-c", "--convert", action='store_true',
                    help="convert to csv")
    # get command line arguments
    args = parser.parse_args()

    # process argument
    if args.loglevel is not None:
        loglevel = getattr(logging, args.loglevel.upper(), None)
    logging.basicConfig(format=LOG_FORMAT, level=loglevel)
    logger = logging.getLogger(__name__)

    start_time = datetime.now()
    infile = args.datafile
    _, basename = fu.get_dir_basename(infile)
    outfile = f'{args.outdir}/{basename}-preprocessed.csv'
    assert os.path.isfile(infile), f"{infile} does not exist"

    logger.info(f'loading data frame from {infile}')
    df = pd.read_csv(infile, ",", parse_dates=["review_date"])
    logger.info(f'finished loading dataframe {infile}')
    logger.info(f'original dataframe length: {len(df)}')

    logger.info(f'starting text pre-processing')
    tp = TextPreprocessor(text_columns=["review_headline", "review_body"],
                          columns_to_drop=['marketplace', 'vine', 'verified_purchase', 'customer_id', 'review_id', 'product_id', 'product_parent', 'product_title', 'product_category'],
                          stop_word_remove_list=STOP_WORDS_TO_REMOVE,
                          retain_original_columns=args.retain,
                          custom_preprocessor=[remove_amazon_tags, remove_http_links])
    df = tp.preprocess_data(df)
    logger.info(f'pre-processing finished - new dataframe length: {len(df)}')

    logger.info(f'writing dataframe to {outfile}')
    df.to_csv(outfile, doublequote=True, index=False)
    end_time = datetime.now()
    total_time_min = round((end_time - start_time).total_seconds() / 60, 2)
    logger.info(f"Total time (minutes): {total_time_min}")


if __name__ == '__main__':
    main()