import csv
import os
import logging
import re


log = logging.getLogger(__name__)


def convert_tsv_to_csv(infile: str, outfile: str, sampler = None):
    """
    Read a tsv file line by line then covert it into a readable csv file
    :param infile: input TSV file
    :param outfile: output CSV file
    :param sampler - Sampler to reduce the output file size
    :return:
    """

    print(f"Converting {infile} to {outfile} with sampling {sampler}")

    if os.path.isfile(infile):

        counter = 0
        with open(infile, "r+") as old_f, open(outfile, "w") as new_f:
            writer = csv.writer(new_f)
            for line in old_f:
                # never sample 0 because that's the header column
                if sampler is None or sampler.collect(counter):
                    data = line.strip('\n').split('\t')
                    writer.writerow(data)
                counter += 1
        print(f"Finished converting {infile} to {outfile} with sampling {sampler}")
    else:
        print(f'File not found: {infile}')


def get_report_filename(infile: str, outpath:str="reports/") -> str:
    """
    Takes the input file name and construct the output report filename
    :param infile:
    :return:
    """
    matches = re.findall(r'/([\w-]+)\.csv', infile)
    outpath = re.sub(f'/$', '', outpath)
    outfile = f'{outpath}/{matches[0]}-report.csv'
    log.debug(f'Output filename: {outfile}')
    return outfile


def get_dir_basename(infile:str) -> (str, str):
    """
    get the directory and basename of a filename
    :param infile:
    :return:
    """
    dir_match = re.findall(r'([/\w-]+)/[\w-]+\.[a-zA-Z]+', infile, re.IGNORECASE)
    file_match = re.findall(r'/*([\w-]+)\.[a-zA-Z]+', infile, re.IGNORECASE)
    if len(dir_match) > 0:
        return dir_match[0], file_match[0]
    return None, file_match[0]






