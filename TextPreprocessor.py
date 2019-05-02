import pandas as pd
from pandas import DataFrame
from pandas import Series
import logging
import text_util as tu
import df_util as dfu

logger = logging.getLogger(__name__)
# counter for debugging
counter = 0


class TextPreprocessor:

    def __init__(self,
                 text_columns,
                 columns_to_drop=None,
                 to_lowercase=True,
                 remove_newlines=True,
                 remove_amazon_tags=True,
                 remove_html_tags=True,
                 remove_accented_chars=True,
                 expand_contractions=True,
                 remove_special_chars=True,
                 stem_text=True,
                 remove_stop_words=True,
                 create_original_columns=False):
        """

        :param text_columns: list of columns to process. required
        :param columns_to_drop: list of columns to drop. optional
        :param to_lowercase:
        :param remove_newlines:
        :param remove_amazon_tags:
        :param remove_html_tags:
        :param remove_accented_chars:
        :param expand_contractions:
        :param remove_special_chars:
        :param stem_text: True if stem text, False if lemmatize
        :param remove_stop_words:
        :param create_original_columns:
        """
        assert text_columns is not None, "text_column_name is required"

        self.text_columns = text_columns
        self.columns_to_drop = columns_to_drop
        self.to_lowercase = to_lowercase
        self.remove_newlines = remove_newlines
        self.remove_amazon_tags = remove_amazon_tags
        self.remove_html_tags = remove_html_tags
        self.remove_accented_chars = remove_accented_chars
        self.expand_contractions = expand_contractions
        self.remove_special_chars = remove_special_chars
        self.stem_text = stem_text
        # we are either going to stem or lemmatize
        if not self.stem_text:
            self.lemmatize_text = False
        else:
            self.lemmatize_text = True
        self.remove_stop_words = remove_stop_words
        self.retain_original_columns = create_original_columns


    def normalize_text(self, row: Series) -> Series:
        """
        Noramlize text
        1. make lower case
        2. remove accents
        3. remove special characters
        """
        assert row is not None, "row is None"

        global counter
        counter += 1
        if counter % 5000 == 0:
            logger.info(f'normalizing row: {counter}')

        for column in self.text_columns:
            text = row[column]
            # text = row.text
            # logger.debug(row.describe())
            logger.debug(f'column: [{column}] text: [{text}]')

            if text is not None and len(text) > 0:

                # use regex to make lower case
                if self.to_lowercase:
                    text = tu.make_lowercase(text)
                if self.remove_newlines:
                    text = tu.remove_newlines(text)
                if self.remove_amazon_tags:
                    text = tu.remove_amazon_tags(text)
                if self.remove_html_tags:
                    text = tu.remove_html_tags(text)
                if self.remove_accented_chars:
                    text = tu.remove_accented_chars(text)
                if self.expand_contractions:
                    text = tu.expand_contractions(text)
                if self.remove_special_chars:
                    text = tu.remove_special_chars(text)
                if self.stem_text:
                    text = tu.stem_text(text)
                if self.lemmatize_text:
                    text = tu.lemmatize_text(text)
                # we have to do this after expanding contractions so it doesn't remove words like don't or shouldn't
                if self.remove_stop_words:
                    text = tu.remove_stop_words(text)

            logger.debug(f'clean text from column [{column}] [{text}]')
            row[column] = text
        return row

    def preprocess_data(self, df: DataFrame) -> DataFrame:
        """
        Do the following:
            * strip columns
            * normalize text
        """
        logger.info("start preprocessing data")

        logger.info(f"column count before dropping columns: {len(df.columns)}")
        if self.columns_to_drop:
            df = dfu.drop_columns(df, self.columns_to_drop)
        logger.info(f"column count after dropping columnes: {len(df.columns)}")

        # drop null values before processing
        logger.info(f"original row count: {len(df)}")
        df = df.dropna()
        logger.info(f"row count after dropping na: {len(df)}")

        logger.info(f"column count before duplicating columns: {len(df.columns)}")
        if self.retain_original_columns:
            df = dfu.duplicate_columns(df, self.text_columns, reorder=True)
        logger.info(f"column count after duplicating columns: {len(df.columns)}")


        # reset counter
        global counter
        counter = 0
        df = df.apply(self.normalize_text, axis=1)

        # after normalizing, we are enow seeing some columns with 0 length text - they seem to be legit
        # make sure we remove anything that got stripped completely
        logger.info(f"row count before dropping empty values: {len(df)}")
        df = dfu.drop_empty_columns(df, self.text_columns)
        logger.info(f"row count after dropping empty values: {len(df)}")

        logger.info("finished preprocessing data")
        logger.info(df.info())
        logger.info(df.head())

        return df

    def convert_to_csv(self, df: DataFrame, outfile: str):
        """
        convert df to cvs
        """
        df[self.text_column_name].apply(tu.remove_newlines)
        df.to_csv(outfile, index=False, doublequote=True)
