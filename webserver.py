import os
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ElementTree
import pandas as pd
import numpy as np
import yaml
from pathlib import Path
from datetime import datetime
from flask import Flask, flash, request, redirect, url_for, make_response

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
    try: 
        byte_to_string = request.data.decode("utf-8")
        clean_xml = byte_to_string.replace("\r\n", "")
        tree = ET.ElementTree(ET.fromstring(clean_xml))
        get_data_xml(tree)
        
    except:
        print('SUCCESS START UP')

    #This section is important in response to the AcquiSuite response. This XML response is the only way to 
    #properly respond to the AcquiSuite in which it will receive a "SUCCESS" indicator and delete backlogged files.
    #This works by sending a properly formatted XML string with HTML style headers. The biggest issue was that 
    #Content-Type is defaulted to text/html for the AcquiSuite, so that needed to be changed. 
    resp = make_response("<?xml version=\"1.0\"?>\n<DAS>\n<result>SUCCESS</result>\n</DAS>\n")
    resp.headers['Status'] = '200 OK'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Content-Type'] = 'text/xml'
    return resp

#TODO: Need to separate csv files by Point rather than Address
#TODO: Update for yaml config
def get_data_xml(xmlTree):
    
    #Initialization of DataFrame
    gbl_tbl = pd.DataFrame(columns=["Address", "Point", "Name", "Value", "Time"])
    
    #Getting the root of the xmlTree and initializing address
    root = xmlTree.getroot()
    address = 0
    for d in root.iter('device'):
        address = d.find('address').text
        
    #String conversions for proper file naming convention
    #This section assumes device address will never exceed 999
    if int(address) < 10:
        address = "00" + address
    elif int(address) >= 10 and int(address) < 100:
        address = "0" + address

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
            if "value" in child.attrib:
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
                
                #Checking for duplicates within the file and removing them if found, also appending new file to old
                if os.path.isfile('data/acquisuite_' + address + "_" + point + "_" + year + "_" + month + '.csv'):
                    existing = pd.read_csv('data/acquisuite_' + address + "_" + point + "_" + year + "_" + month + '.csv')
                    existing = existing.append(gbl_tbl)
                    existing = existing[~existing.duplicated()]
                    gbl_tbl = existing
                
                #Converts the DataFrame into a csv file
                gbl_tbl.to_csv('data/acquisuite_' + address + "_" + point + "_" + year + "_" + month + '.csv', index=False)
                    
    #Dropping NaN values in Value column
    gbl_tbl = gbl_tbl.dropna(subset=['Value'])
        
    #Converts the DataFrame into a csv file
    gbl_tbl.to_csv('data/acquisuite_' + address + '_data.csv', index=False)
    
    #Code snippet for getting raw xml file examples
    #xmlTree.write('raw_xml_data/' + address + "_raw.xml")
    return 'SUCCESS'

@app.route('/get_data')
#start and end are times, and must be in the format YEAR-MONTH-DAY (ex: 2019-06-17)
#NOTE: the csv files are formated as ADDRESS_data.csv (ex: 250_data.csv)
#NUANCES: start and end must have their hour and smaller units separated by "_" (ex: 2019-06-17_02:55:00)
def get_data(start, end='N/A'):

    start = request.args.get('start')
    #TODO: check if we can only enter one parameter if have default
    #end = request.args.get('end')
    
    #Opens our config file, currently in yaml format
    stream = file('config.yaml', 'r')
    
    #Initializing arrays 
    address = np.array([])
    points = np.array([])
    
    #Mapping points to custom for table output
    custom_map = {}
    
    #Running through all sub-documents in yaml
    for data in yaml.load_all(stream):
        address = np.append(address, data['address'])
        points = np.append(points, data['points'][0])
        custom_map[[data['address'], data['points'][0]]] = data['points'][1]
                   
    #Starts reading and sorting our table
    #TODO: Fix with different csv format! 
    table = pd.read_csv("data/" + str(address) + "_data.csv")
    table = table[table['Point'].isin(points)]
    
    #Applies datetime conversion to time column in DataFrame
    table["Time"] = table["Time"].apply(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'))
    
    #Options for entering an end value or not
    if end == 'N/A':
        try:
            start = start.replace("_", " ")
            start = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
            
            #Filtering now by time
            table = table[(table['Time'] >= start)]
        except:
            return "Wrong format! Look at comments in webserver.py for an example!"
    else:
        #Changes user string input for start/end to datetime format
        #NOTE: remember the format for entering params! Look at comments above. This is because entering 
        #flask params in a url doesn't take whitespace well, so it is replaced with "_".
        try:
            start = start.replace("_", " ")
            end = end.replace("_", " ")
            start = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
            end = datetime.strptime(end, '%Y-%m-%d %H:%M:%S')

            #Filtering now by time
            table = table[(table['Time'] >= start) & (table['Time'] <= end)]
        except:
            return "Wrong format! Look at comments in webserver.py for an example!"
    
    #Dropping NaN values in Value column
    table = table.dropna(subset=['Value'])
    
    #Applying mapping
    custom = table.apply(lambda x: custom_map[[x["Address"], x["Point"]]], axis=1)
    table['Custom'] = custom
    
    #Currently returns an html table to the webserver, will eventually need to configure to SkySpark
    return table.to_html(header="true", table_id="table")

    #EXAMPLE URL: http://localhost:8080/get_data/2019-07-25_18:14:00/

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
    
    
    
    
    
    
    
    
    
    