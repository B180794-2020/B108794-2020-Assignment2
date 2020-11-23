#!/usr/bin/python3
import os
import re
import subprocess

import pandas as pd

# important to import readline despite none of its functions being spesifically called:
# enables the use of backspace in the terminal without them being part of user inputs
import readline

# Finding path to file location and directory, changing working directory to location
abspath = os.path.abspath(__file__)
dir = os.path.dirname(abspath)
os.chdir(dir)


# Defining main body that will run the other functions in correct order/manner
def main():
    new_search = True
    while new_search:
        # Get user input of Taxonomy and Protein for search, choose to continue with search or not
        mysearch = user_search()
        # Conduct search and fetch number of results, evaluate is there the required mininum of 3 seq
        progress, max_seq, number_of_results = fetch_data(mysearch)

        if progress:
            filename = fetch_fasta(mysearch, number_of_results)
            aligned, consensus, blastResults = conserved_sequence_analysis(filename, max_seq)
            accnumbers, save = plot_top_250(filename, blastResults, aligned, 250)
            find_motifs(aligned, accnumbers)
        else:
            print("Search has been cancelled")

        new_search = yes_no("\033[1;32;40m Would you like to do another search? Y/N ", "Exiting")
        print("\033[1;37;40m ")


# function for determining paramaters for user search
def user_search():
    # declaring variabless in case somehow exit loop without declaring them
    tax = family = ""
    # loop for giving an option to change search after input in case a mistake was made
    progress = False
    while not progress:
        # user input for Protein family and Taxonomy
        # if keyboard is interrupted loop is broke, one or the other == "", progress is therefore False
        try:
            family = input("\033[1;32;40m Enter protein family: ")
            print("\033[1;37;40m ")
        except KeyboardInterrupt:
            print("Error: Keyboardinterrupt")
            return "", False

        try:
            tax = input("\033[1;32;40m Enter Taxanomic group: ")
            print("\033[1;37;40m ")
        except KeyboardInterrupt:
            print("Error: Keyboardinterrupt")
            return "", False

        print(f"Protein family: {family}, Taxanomic group: {tax}")
        # choice to continue or not
        progress = yes_no("Are these correct? Y/N: ", "Please re-enter protein family and group.")

        # test to see if blank paramaters
        if tax.strip(" ") == "" or family.strip(" ") == "":
            print("Warning one of the fields was left blank. Please re-enter the Protein family and Taxanomic group.")
            progress = False
    # promting the user to see if they want to exclude partial and or predicted sequences from their analysis

    pred = part = ""
    ex_predict = yes_no("Do you wish to exclude predicted sequences? Y/N: ", "")
    ex_partial = yes_no("Do you wish to exclude partial sequences? Y/N: ", "")

    if ex_predict:
        pred = "NOT predicted NOT hypothetical"
    if ex_partial:
        part = "NOT partial"
    # Term that will be searched for on NCBI
    mysearch = f"{tax}[Organism] AND {family}[Protein] {pred} {part}"

    # return the search term
    return mysearch


# function for fetching the data of how many search results there are for the search
def fetch_data(mysearch):
    # calling shell command of esearch with specified paramaters
    # piping results into grep that selects titles of each result
    try:
        print("Conducting search...")
        res = subprocess.check_output(
            f"esearch -db protein -query \"{mysearch}\" | efetch -format docsum | grep -E \"<AccessionVersion>|<Title>\" ",
            shell=True)
    except subprocess.CalledProcessError:
        print("Error: There were no results for search")
        progress = False
        return progress, 0, 0

    # find [species names] that are in square brackets and accession numbers
    species = re.finditer(r"\[.*?\]", str(res))
    accession = re.finditer(r'<AccessionVersion>.*?</AccessionVersion>', str(res))
    # put species into a list wihout the brackets
    species_list = []
    acession_list = []

    for i in species:
        species_list.append(i.group(0).strip("[]"))
    for i in accession:
        acession_list.append(i.group(0).strip("<AccessionVersion></AccessionVersion>"))
    # total number of results in the list and number of unique species names
    total_results = len(species_list)
    species_number = len(set(species_list))
    # conditions for continuing process
    max_sequences = 1000
    max_species = 500
    progress = True
    # prompt user to continue based on n of seq and species
    print(f"Number of Sequences: {total_results}\nNumber of Species: {species_number}")

    if total_results > max_sequences:
        progress = yes_no("Warning! Search resulted in more than 1000 sequences. \n do you wish to continue? Y/N: ",
                          "Exiting")
    if species_number > max_species:
        progress = yes_no("Warning! Search resulted in more than 500 species. \n do you wish to continue? Y/N: ",
                          "Exiting")
    if total_results < 3:
        print("Not enough sequences in search result to conduct analysis")
        progress = False

    return progress, max_sequences, total_results


def fetch_fasta(mysearch, number_of_results):
    # let user choose file name where fasta will be saved
    filename = input("\033[1;32;40m Enter filename: ").lower()
    print("\033[1;37;40m ")
    # get fasta files
    print("Fetching Fasta files from NCBI protein database...")
    subprocess.call(f"esearch -db protein -query \"{mysearch}\" | efetch -format fasta > {filename}", shell=True)
    remove = False
    # Only gives option to remove seq if there are more than 3 of them
    if number_of_results > 3:
        remove = yes_no(
            "Do you wish to remove duplicate sequences? This will also remove isoforms of the same protein. Y/N: ", "")
    if remove:
        out = filename + ".keep"
        # EMBOSS skip redundant to identify duplicate sequences, keeps longer of two if identical
        print("Removing redundant...")
        subprocess.call(
            f"skipredundant -maxthreshold 100.0 -minthreshold 100.0 -mode 2 -gapopen 0.0 -gapextend 0.0 -outseq {out} -datafile EBLOSUM62 -redundant \"\" {filename}",
            shell=True)
        # Counting the number of sequences in the .keep file
        print("Checking remaining files...")
        with open(out) as f:
            sequence_count = 0
            lines = f.readlines()
            for line in lines:
                # each line that starts with a > should indicate a sequence
                if ">" in line:
                    sequence_count += 1
        # checking that there are atleats 3
        print(f"Remaining files: {sequence_count}")
        if sequence_count < 3:
            print("Not enough sequences after removing redundant sequences.")
            print("Reverting to using original full list of sequences.")
            subprocess.call(f"rm {out}", shell=True)
            return filename

        return out
    else:
        return filename


def conserved_sequence_analysis(filename, max_seq):
    # Names of files that will be created
    aligned = filename + ".aligned"
    consensus = filename + ".con"
    blast_results = filename + ".blast"

    # sequence alignment and finding a consensus sequence
    print("Aligning sequences...")
    subprocess.call(f"clustalo --force --threads 8 --maxnumseq {max_seq} -i {filename} -o {aligned}", shell=True)
    print("Finding consensus sequence...")
    subprocess.call(f"cons -datafile EBLOSUM62 -sequence {aligned} -outseq {consensus}", shell=True)

    # BLAST
    print("Constucting Blast database...")
    subprocess.call(f"makeblastdb -in {filename} -dbtype prot -out {filename}", shell=True)
    print("Conducting blast search with consensus sequence...")
    subprocess.call(f"blastp -db {filename} -query {consensus} -outfmt 7 > {blast_results}", shell=True)

    return aligned, consensus, blast_results


def plot_top_250(filename, blast_results, aligned, n):
    # setting headings for dataframe, assumes blast with n rows and 12 columns (-outfmt 7)
    headings = ["queryacc.", "subjectacc.", "% identity", "alignment_length",
                "mismatches", "gap_opens", "q.start", "q.end", "s.start",
                "s.end", "e-value", "bit_score"]
    # setting up dataframe using pandas
    df = pd.read_csv(f"{blast_results}", skiprows=5, names=headings, sep="\t")
    # sorting according to bitscores
    df.sort_values('bit_score', ascending=False, inplace=True)

    # taking top n number of sequences
    max_seq = n
    dfsubset = df[0:max_seq]

    print(f"Finding top {n} for plotting sequence conservation...")
    # collecting accession numbers of the top 250
    acc_numbers = dfsubset["subjectacc."].tolist()

    # removing nan incase there are less than n sequences in the initial test
    if len(acc_numbers) < n:
        acc_numbers = acc_numbers[:-1]

    # filenames
    top250 = filename + ".250"
    top_fasta = top250 + ".fasta"

    # creating a file containing the accnum of top 250
    with open(top250, 'w') as f:
        for num in acc_numbers:
            f.write(f"{num}\n")

    # preparing for a new seach of just the top 250
    print(f"Fetching top {n} for plotting sequence conservation...")
    subprocess.call(f"/localdisk/data/BPSM/Assignment2/pullseq -i {aligned} -n {top250}> {top_fasta}", shell=True)

    save = input("\033[1;32;40m Choose filename for saving Conservation plot: ") + ".plot"
    print("\033[1;37;40m ")
    # searching for the top 250, aligning them and plotting the conservation using EMBOSS plotcon
    subprocess.call(f"plotcon -scorefile EBLOSUM62 -winsize 4 -graph x11 -goutfile {save} {top_fasta}", shell=True)

    # removing temporary files that were generated for each to be taken as an imput
    subprocess.call(f"rm {top250}", shell=True)
    subprocess.call(f"rm {top_fasta}", shell=True)

    # returns a list containing the top accnumbers
    return acc_numbers, save


def find_motifs(aligned, accnumbers):
    print(f"Seaching for protein motifs...")
    motif_list = []

    # Blast may have more than one alignment for each sequence, multiple times diffrentiate by ID
    seq_id = 0

    # creating temp files for input into pullseq containing the sequence accnumber
    for number in accnumbers:
        seq_id += 1
        filename = number + "." + str(seq_id)
        with open(filename, "w") as f:
            f.write(f"{number}")

        # file names for patmatmotif output and temp
        motifs = filename + ".motif"
        temp = "temp"

        # finding the fasta of a protein based on accesion number and storing it in a temporary file
        subprocess.call(f"/localdisk/data/BPSM/Assignment2/pullseq -i {aligned} -n {filename} > {temp}", shell=True)
        subprocess.call(f"patmatmotifs {temp} -outfile {motifs}", shell=True, stdout=open(os.devnull, 'wb'))

        # removing temporary files that were generated for each to be taken as an imput
        subprocess.call(f"rm {filename}", shell=True)
        subprocess.call(f"rm {temp}", shell=True)
        motif_list.append(motifs)

    my_dic = {}
    # Constructing a dictinary containing the information from patmatmotifs
    for motif in motif_list:
        # open report file of patmat, scan each line for key words, add only value
        with open(motif) as f:
            lines = f.readlines()
            # If no motifs then return as empty strings
            mot = length = start = end = ""
            for line in lines:
                if "Length" in line:
                    length = int(line.split(" ")[2].strip("\n"))
                if "Start" in line:
                    start = int(line.split(" ")[3])
                if "End" in line:
                    end = int(line.split(" ")[3])
                if "Motif" in line:
                    mot = line.split(" ")[2].strip("\n")
            my_dic[motif] = [mot, length, start, end]

        # remove the report file after information has been extracted
        subprocess.call(f"rm {motif}", shell=True)

    headings = ["Motif", "Length", "Start", "End"]
    df = pd.DataFrame.from_dict(my_dic, orient='index', columns=headings)

    save = input("\033[1;32;40m Input filename for motifs: ")
    print("\033[1;37;40m ")

    with open(save, "w") as f:
        df.to_string(f)
    return True


def yes_no(question, reprompt):
    # list of possible approved answers for each option
    yes = ["y", "Y", "Yes", "YES", "yes"]
    no = ["n", "N", "No", "NO", "no"]

    invalid = False

    # infinite loop if an answer other than one in the list is given
    while not invalid:
        while True:
            try:
                answer = input(f"\033[1;32;40m {question}")
                print("\033[1;37;40m ")
                break
            except KeyboardInterrupt:
                print("Error: KeyboardInterrupr")
                print("Try again: ")

        # returns true or false depending on answer
        if answer in yes:
            return True
        elif answer in no:
            print(reprompt)
            return False

        print("Invalid input. Please answer Yes or No")


if __name__ == '__main__':
    main()

