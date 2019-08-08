import os
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ElementTree
import pandas as pd
import numpy as np
import yaml
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, flash, request, redirect, url_for, make_response
import re

logging.basicConfig(filename="web.log", level=logging.DEBUG, format='%(asctime)s:%(levelname)s:%(message)s')
#BIG NOTE: PLEASE TURN OFF FIREWALL TO HAVE ACQUISUITE WORK! Need to figure out a protocol to allow AcquiSuite. 
                  
app = Flask(__name__)
app.secret_key = "super secret"
@app.route('/', methods = ['GET', 'POST'])
def default():
    print("--Entering default()--")
    print("HEADERS: ", request.headers)
    print("REQ_PATH: ", request.path)
    print("ARGS: ", request.args)
    print("DATA: ", request.data)
    print("FORM: ", request.form)
    
    #This block takes the request.data, which is encoded in bytes, and decodes it to a string and cleans it. We then make it an XML tree.
    #NOTE: When debugging, remove the try-except block! 
    try:
        byte_to_string = request.data.decode("utf-8")
        clean_xml = byte_to_string.replace("\r\n", "")
        tree = ET.ElementTree(ET.fromstring(clean_xml))
        get_data_xml(tree)
    except:
        print("START UP")
        logging.debug("STARTING UP WEBSERVER OR SERVER BREAKDOWN")

    #This section is important in response to the AcquiSuite response. This XML response is the only way to 
    #properly respond to the AcquiSuite in which it will receive a "SUCCESS" indicator and delete backlogged files.
    #This works by sending a properly formatted XML string with HTML style headers. The biggest issue was that 
    #Content-Type is defaulted to text/html for the AcquiSuite, so that needed to be changed. 
    resp = make_response("<?xml version=\"1.0\"?>\n<DAS>\n<result>SUCCESS</result>\n</DAS>\n")
    resp.headers['Status'] = '200 OK'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Content-Type'] = 'text/xml'
    return resp

def get_data_xml(xmlTree):
    #Initialization of DataFrame
    gbl_tbl = pd.DataFrame(columns=["Address", "Point", "Name", "Value", "Time"])
    
    #Getting the root of the xmlTree and initializing address
    root = xmlTree.getroot()
    address = 0
    for d in root.iter('device'):
        address = d.find('address').text
    
    #Mapping points to custom for table output
    custom_map = {}
    
    #Running through all sub-documents in yaml and getting what we need
    for data in yaml.load_all(open('config.yaml', 'r'), Loader=yaml.FullLoader):
        #Mapping through a dictionary with tuples as keys
        add = data['address']
        points = data['points']

        #Edge case where config points are empty
        if points:       
            #yaml regex alterations, mapping with tuples
            for p in points:
                regexed = re.findall('[0-9]+,', p)[0]
                entered = p.replace(regexed + ' ', "")
                point = int(regexed.replace(',', ""))
                custom_map[(add, point)] = entered
        
    #String conversions for proper file naming convention
    #This section assumes device address will never exceed 999
    if int(address) < 10:
        address = "00" + str(address)
    elif int(address) >= 10 and int(address) < 100:
        address = "0" + str(address)

    #How this works: We changed the XML file to a tree, then iterate through the child nodes with "record" as its tag
    for record in root.iter('record'):
        #Get the time of the record entry
        time = record.find('time').text

        #Getting Year/Month from time string
        year = time[:4]
        month = time[5:7]
        #Iterate through all points within the record
        for child in record:
            #This is mainly to get the points, we can alter to specify other info like error messages
            if "value" in child.attrib and child.attrib['value'] != "NULL":
                if custom_map.get((int(address), int(child.attrib['number'])), 'null') != 'null':
                    #Below is for file naming convention, assuming points will not exceed 99
                    point = child.attrib['number']
                    if int(point) < 10:
                        point = "0" + point

                    #Create a DataFrame with line of data (which is really a row right now) to append to main DataFrame
                    tbl = pd.DataFrame(data=[[address, point, 
                                              child.attrib['name'], child.attrib['value'], time]], 
                                       columns=["Address", "Point", "Name", "Value", "Time"])

                    #Appending to gbl_tbl
                    gbl_tbl = gbl_tbl.append(tbl, ignore_index=True)

                    #Dropping NaN values in Value column
                    #gbl_tbl = gbl_tbl.dropna(subset=['Value'])

                    #Applying mapping
                    custom = gbl_tbl.apply(lambda x: custom_map[(int(x["Address"]), int(x["Point"]))], axis=1)
                    gbl_tbl['Custom'] = custom

                    #Checking for duplicates within the file and removing them if found, also appending new file to old
                    if os.path.isfile('data/acquisuite_m' + address + "_p" + point + "_" + year + "_" + month + '.csv'):
                        existing = pd.read_csv('data/acquisuite_m' + address + "_p" + point + "_" + year + "_" + month + '.csv', 
                                               dtype={"Address": str, "Point": str})
                        existing = existing.append(gbl_tbl)
                        existing = existing[~existing.duplicated()]
                        gbl_tbl = existing

                    #Converts the DataFrame into a csv file
                    gbl_tbl.to_csv('data/acquisuite_m' + address + "_p" + point + "_" + year + "_" + month + '.csv', index=False)

                    #Reset gbl_tbl
                    gbl_tbl = pd.DataFrame(columns=["Address", "Point", "Name", "Value", "Time"])
                    
    
    #Code snippet for getting raw xml file examples
    #xmlTree.write('raw_xml_data/' + address + "_raw.xml")
    return 'SUCCESS'

@app.route('/get_data', methods=['GET'])
#start and end are times, and must be in the format YEAR-MONTH-DAY (ex: 2019-06-17)
#NUANCES: start and end must have their hour and smaller units separated by "_" (ex: 2019-06-17_02:55:00)
def get_data():

    #Gathering initial parameters
    address = request.args.get('address')
    point = request.args.get('point')
    start = request.args.get('start')
    end = request.args.get('end')
    
    #This section assumes device address will never exceed 999
    if int(address) < 10:
        address = "00" + str(address)
    elif int(address) >= 10 and int(address) < 100:
        address = "0" + str(address)

    #Assuming point will not exceed 99
    if int(point) < 10:
        point = "0" + point
        
    #Default value for end is current time
    if end == 'now':
        end = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    #Changes user string input for start/end to datetime format
    #NOTE: remember the format for entering params! Look at comments above. This is because entering 
    #flask params in a url doesn't take whitespace well, so it is replaced with "_".
    try:
        start = start.replace("_", " ")
        end = end.replace("_", " ")
        start = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
        end = datetime.strptime(end, '%Y-%m-%d %H:%M:%S')
    except:
        #Append malformed argument?
        logging.debug('Wrong datetime format entered in URL argument. \n\tstart: %s\n\tend: %s' % (start, end))
        return "Wrong format! Look at comments in webserver.py for an example!" 
    
    #Initializing global table
    gbl_tbl = pd.DataFrame(columns=["Address", "Point", "Name", "Value", "Time"])

    #Increasing start date by a month each time to get all values until current year-month
    counter_date = start
    month = ""   
    
    counter_year = int(counter_date.strftime("%Y"))
    counter_month = int(counter_date.strftime("%m"))
    end_year = int(end.strftime("%Y"))
    end_month = int(end.strftime("%m"))
    
    #Datetime iteration until endtime
    while (counter_year < end_year or counter_month <= end_month):
        #Time to string conversions
        if counter_date.month < 10:
            month = "0" + str(counter_date.month)

        #Reading csv files by month
        if os.path.isfile('data/acquisuite_m' + address + "_p" + point + "_" + str(counter_date.year) + "_" + month + '.csv'):
            his = pd.read_csv('data/acquisuite_m' + address + "_p" + point + "_" + \
                  str(counter_date.year) + "_" + month + '.csv',
                  dtype={"Address": str, "Point": str})

            #Appending data
            gbl_tbl = gbl_tbl.append(his)   
        
        #Incrementing counter by month
        counter_date = datetime(counter_date.year + int(counter_date.month / 12), ((counter_date.month % 12) + 1), 1)
        
        counter_year = int(counter_date.strftime("%Y"))
        counter_month = int(counter_date.strftime("%m"))
  
    #If the table is empty, that means there was nothing available for given address/point combo.
    if gbl_tbl.empty:
        logging.debug("No file with requested address and point combination.")
        return("No file with this address and/or point. Look at the data folder for available files.") 
    
    #Applies datetime conversion to time column in DataFrame
    gbl_tbl["Time"] = gbl_tbl["Time"].apply(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'))
    
    #Filtering now by time
    gbl_tbl = gbl_tbl[(gbl_tbl['Time'] >= start) & (gbl_tbl['Time'] <= end)]
    
    #return gbl_tbl.to_html(header="true", table_id="table")
    return gbl_tbl.to_csv(index=False)

    #EXAMPLE URL: http://localhost:8080/get_data?address=37&point=0&start=2019-07-31_23:18:01&end=2019-07-31_23:23:01
    #EXAMPLE URL: http://localhost:8080/get_data?address=37&point=0&start=2019-07-31_23:18:01&end=now

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
    
    
#Additional routes to retreive debugging info or something, some logging route
#Look into logging import in Python
#Look into gzip (gz) for compression
    
    
    
    
    
    
