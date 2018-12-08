#!/usr/bin/python
# coding:utf-8
# author: itnihao
# mail: itnihao#qq.com
# url: https://github.com/zabbix-book/zabbix_mail_with_graph

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

from pyzabbix import ZabbixAPI
import os
import argparse
import logging
import datetime
import requests
import tempfile
import re
import urllib3


class Zabbix_Graph(object):
    """ Zabbix_Graph """

    def __init__(self, url=None, user=None, pwd=None, timeout=None):
        urllib3.disable_warnings()
        if timeout == None:
            self.timeout = 1
        else:
            self.timeout = timeout
        self.url = url
        self.user = user
        self.pwd = pwd
        self.cookies = {}
        self.zapi = None

    def _do_login(self):
        """ do_login """
        if self.url == None or self.user == None or self.pwd == None:
            print "url or user or u_pwd can not None"
            return None
        if self.zapi is not None:
            return self.zapi
        try:
            zapi = ZabbixAPI(self.url)
            zapi.session.verify = False
            zapi.login(self.user, self.pwd)
            self.cookies["zbx_sessionid"] = str(zapi.auth)
            self.zapi = zapi
            return zapi
        except Exception as e:
            print "auth failed:\t%s " % (e)
            return None

    def _is_can_graph(self, itemid=None):
        self.zapi = self._do_login()
        if self.zapi is None:
            print "zabbix login fail, self.zapi is None:"
            return False
        if itemid is not None:
            """
            0 - numeric float; 
            1 - character; 
            2 - log; 
            3 - numeric unsigned; 
            4 - text.
            """
            item_info = self.zapi.item.get(
                filter={"itemid": itemid}, output=["value_type"])
            if len(item_info) > 0:
                if item_info[0]["value_type"] in [u'0', u'3']:
                    return True
            else:
                print "get itemid fail"
        return False

    def get_graph(self, itemid=None):
        """ get_graph """
        if itemid == None:
            print "itemid can not None"
            return "ERROR"

        if self._is_can_graph(itemid=itemid) is False or self.zapi is None:
            print "itemid can't graph"
            return "ERROR"

        if len(re.findall('4.0', self.zapi.api_version())) == 1:
                graph_url = "%s/chart.php?from=now-1h&to=now&itemids[]=%s" % (
                    zbx_url, itemid)
        else:
            graph_url = "%s/chart.php?period=3600&itemids[]=%s" % (
                zbx_url, itemid)

        try:
            rq = requests.get(graph_url, cookies=self.cookies,
                              timeout=self.timeout, stream=True, verify=False)
            if rq.status_code == 200:
                imgpath = tempfile.mktemp()
                with open(imgpath, 'wb') as f:
                    for chunk in rq.iter_content(1024):
                        f.write(chunk)
                    return imgpath
            rq.close()
        except:
            return "ERROR"

class Mail(object):
    """ send mail"""

    def __init__(self, server=None, port=None, user=None, pwd=None):
        self.server = server
        self.port = port
        self.user = user
        self.pwd = pwd
        self.logpath = '/tmp/.zabbix_alert'

    def _connect(self):
        """ Connect to SMTP server """
        if self.server == None or self.port == None or self.user == None or self.pwd == None:
            print "Error smtp_server=None, smtp_port=None, smtp_user=None, smtp_u_pwd=None"
            return False
        try:
            if self.port == 465:
                smtp = smtplib.SMTP_SSL()
                smtp.connect(self.server, self.port)
            elif self.port == 587:
                smtp = smtplib.SMTP()
                smtp.connect(self.server, self.port)
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo
            else:
                smtp = smtplib.SMTP()
                smtp.connect(self.server, self.port)
            smtp.login(self.user, self.pwd)
            return smtp
        except Exception as e:
            print "Connect to smtp server error:\t%s" % (e)
            return False
        return True

    def Send(self, receiver, subject, content, img=None):
        """ Send mail to user """
        smtp_connect = self._connect()
        if smtp_connect == None or smtp_connect == False:
            return

        if img == None:
            """send with graph"""
            msg = MIMEText(content, _subtype='plain', _charset='utf-8')
            msg['Subject'] = unicode(subject, 'UTF-8')
            msg['From'] = self.user
            msg['to'] = receiver
            try:
                smtp_connect.sendmail(
                    self.user, receiver, msg.as_string())
            except Exception as e:
                print "send mail error:\t%s" % (e)
        else:
            """send with graph"""
            msg = MIMEMultipart('related')
            msg['Subject'] = unicode(subject, 'UTF-8')
            msg['From'] = self.user
            msg['to'] = receiver

            content = content.replace("\n", "<br/>")
            content_html = """\
            <p>%s<br/>
                <img src="cid:monitor_graph">
            </p>""" % (content)

            msg_html = MIMEText(
                content_html, _subtype='html', _charset='utf-8')

            with open(img, 'rb') as f_img:
                read_img = f_img.read()
            msg_img = MIMEImage(read_img, 'png')
            msg_img.add_header('Content-ID', '<monitor_graph>')
            msg_img.add_header('Content-Disposition', 'inline', filename=img)
            msg.attach(msg_html)
            msg.attach(msg_img)

            try:
                smtp_connect.sendmail(self.user, receiver, msg.as_string())
            except Exception as e:
                print "send mail error:\t%s" % (e)
            finally:
                os.remove(img)

        smtp_connect.close()
        self.log(receiver, subject, content)
        print 'send ok'

    def log(self, receiver, subject, content):
        """ log """
        if not os.path.isdir(self.logpath):
            os.makedirs(self.logpath)

        # write log
        try:
            current_time = datetime.datetime.now()
            current_day = current_time.strftime('%Y-%m-%d')
            current_day_log = self.logpath + '/' + str(current_day) + '.log'
            logging.basicConfig(filename=current_day_log, level=logging.DEBUG)
            logging.info('*' * 130)
            logging.debug(str(
                current_time) + '\nsend mail to user:\t{0}\nsubject:\t\n{1}\ncontent:\t\n{2}'.format(receiver, subject, content))
            if os.getuid() == 0:
                os.system('chown zabbix.zabbix {0}'.format(current_day_log))
        except:
            pass

        # remore log 7 days ago
        try:
            days_ago_time = current_time - datetime.timedelta(days=7)
            days_ago_day = days_ago_time.strftime('%Y-%m-%d')
            days_ago_log = self.logpath + '/' + str(days_ago_day) + '.log'
            if os.path.exists(days_ago_log):
                os.remove(days_ago_log)
        except:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='send mail to user for zabbix alerting')
    parser.add_argument('receiver', action="store",
                        help='user of the mail to send')
    parser.add_argument('subject', action="store",
                        help='subject of the mail')
    parser.add_argument('content', action="store",
                        help='content of the mail')
    parser.add_argument('withgraph', action="store", nargs='?',
                        default='None', help='The Zabbix Graph for mail')

    args = parser.parse_args()
    receiver = args.receiver
    subject = args.subject
    content = args.content
    withgraph = args.withgraph
    img = "ERROR"
    itemid = "0"

    # QQ enterprise
    # smtp_server = 'smtp.exmail.qq.com'
    # smtp_port = 25
    # smtp_user = 'itnihao_zabbix@itnihao.com'
    # smtp_u_pwd = '1234567890'

    # 163 Mail
    # smtp_server = 'smtp.163.com'
    # smtp_port = 25
    # smtp_user = 'itnihao_zabbix@163.com'
    # smtp_u_pwd = '1234567890'

    #-----------------------------------------------------------------------------------#
    # Mail Server (mail.qq.com), you should set it with you mail server information
    smtp_server = 'smtp.qq.com'
    smtp_port = 25
    smtp_user = 'itnihao_zabbix@qq.com'
    smtp_pwd = '1234567890'

    # Zabbix API, you should set it
    zbx_url = 'http://127.0.0.1/zabbix'
    #zbx_url = 'http://127.0.0.1'
    zbx_user = 'Admin'
    zbx_pwd = 'zabbix'
    #-----------------------------------------------------------------------------------#

    #get itemid from action
    split_itemid = re.split("ItemID:\s\d", content)
    pattern = re.compile(r'ItemID:.*')
    str_itemid = pattern.findall(content)
    if len(str_itemid) > 0:
        itemid = str_itemid[0].replace(" ", "").replace("ItemID:", "")

    #get graph from zabbix web
    if withgraph != "None" and itemid != "0":
        down_graph = Zabbix_Graph(
            url=zbx_url, user=zbx_user, pwd=zbx_pwd, timeout=3)
        if down_graph is not None:
            img = down_graph.get_graph(itemid=itemid)

    #send mail
    mail_server = Mail(server=smtp_server, port=smtp_port,
                       user=smtp_user, pwd=smtp_pwd)
    if img == "ERROR":
        mail_server.Send(receiver, subject, content)
    else:
        mail_server.Send(receiver, subject, content, img=img)
    #Action add this ItemID: {ITEM.ID}
