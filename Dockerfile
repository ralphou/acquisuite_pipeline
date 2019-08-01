FROM python:3.7

MAINTAINER Chris Weyandt <cweyandt@lbl.gov>

VOLUME /websvr
WORKDIR /websvr

ADD requirements.txt /

RUN apt-get update
RUN pip install --upgrade pip
RUN pip install -r /requirements.txt
RUN pip install pandas

#CMD [ "python", "./webserver.py" ]
