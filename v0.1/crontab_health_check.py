# coding=utf-8
from email.mime.text import MIMEText
from email.header import Header
from functools import wraps
import smtplib
import psutil
import time
import json

# 邮件配置
SMTP_SERVER = 'smtphm.qiye.163.com'
SMTP_USER = 'hanzhichao@spicespirit.com'
SMTP_PASSWD = 'hanzhichao123'
RECEIVER_LIST = ['superhin@126.com','hanzhichao@spicespirit.com']

EMAIL_SUBJECT = '服务器检查邮件报警！！！'
EMAIL_TPL = ''


# CPU/MEMORY 报警百分比
CPU_WARN_PERCENT = 70
MEM_WARN_PERCENT = 70

# php-fpm 单线程 报警值(M)
RES_WARN = 128

# 日志文件,%s会替换成日期
TODAY = time.strftime('%Y-%m-%d',time.localtime(time.time()))
LOG_FILE = '/var/log/health_check_%s.log' % TODAY


# 用于显示执行时间的装饰器
def _show_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print("start %s ... ..." % func.__name__)
        start_time = time.time()
        func_result = func(*args, **kwargs)
        print("%s 执行时间：%.3fs" % (func.__name__, time.time()-start_time))
        return func_result
    return wrapper
        
# 用于将返回列表整理成字典的装饰器
def _collect_result(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_result = func(*args, **kwargs)
        return {func.__name__: {'status': 'OK', 'process_list': []}} if not func_result else {func.__name__: {'status': 'WARN', 'process_list': func_result}}
    return wrapper
 

@_show_time
@_collect_result
def check_cpu():
    if psutil.cpu_percent(0.01) >= int(CPU_WARN_PERCENT):
        return get_top_process('cpu', 10, True)
    else:
        return []


@_show_time
@_collect_result
def check_mem():
    if psutil.virtual_memory().percent >= int(MEM_WARN_PERCENT):
        return get_top_process('mem', 10, True)
    else:
        return []
        

# 获取mem/cpu占用最高的n个进程
def get_top_process(option='mem',n=10,added=True):
    process_list = []
    for proc in psutil.process_iter():
        process_list.append((proc.name(), proc.memory_percent(), proc.cpu_percent(0.01)))

    process_list.sort(key=lambda process_list:process_list[0]) # 按进程名排序

    if added:
        # 累加相同进程名进程资源占用百分比
        process_list = reduce(
            lambda x,y: x+[y] if x==[] or x[-1][0]!=y[0] else x[0:-1]+[(x[-1][0],x[-1][1]+y[1],x[-1][2]+y[2])],
            [[]] + process_list)

    sort_index = 1 if option.lower() == 'mem' else 2  # 排序列,option=mem,按prcess_list第2列(index=1)排序
    # 将process_list按相应列从大到小排序,无累加-------# todo 先累加再排序
    process_list.sort(key=lambda process_list:process_list[2 if sort_index==1 else 1], reverse=True)
    process_list.sort(key=lambda process_list:process_list[sort_index], reverse=True)
    return process_list[0:n]


@_show_time
@_collect_result
def check_zombie_process():
    zombie_process_list = []
    for proc in psutil.process_iter():
        if proc.status() == 'zombie':
            zombie_process_list.append(
                (proc.name(), proc.status(), proc.create_time(), proc.memory_percent(), proc.cpu_percent(0.01))
                )
    return zombie_process_list


@_show_time
@_collect_result
def check_single_process(process_name='php-fpm'):
    warn_process_list = []
    for proc in psutil.process_iter():
        if proc.name() == process_name:
            if proc.memory_info().res()/1024/1024 >= int(RES_WARN):
                warn_process_list.append(proc.name(), proc.create_time(), proc.memory_info().res(), proc.connections())
        return warn_process_list


@_show_time
def write_log(check_result):
    now= time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
    try:
        with open(LOG_FILE,'ab') as f:
            f.writelines(now + '\t' + check_result)
    except IOError:
        print("写日志文件失败！")

@_show_time
def send_mail(subject=EMAIL_SUBJECT, content=EMAIL_TPL): 
    mail_body = content
    msg = MIMEText(mail_body, 'html', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = SMTP_USER
    msg['To'] = ','.join(RECEIVER_LIST)
    smtp = smtplib.SMTP_SSL()
    smtp.connect(SMTP_SERVER,994)
    smtp.login(SMTP_USER, SMTP_PASSWD)
    for reserver in RECEIVER_LIST:
        smtp.sendmail(SMTP_USER, reserver, msg.as_string())
    smtp.quit()
    print('Email has send out!')


if __name__ == '__main__':
    print("主程序开始")
    start_time = time.time()
    check_result = reduce(
        lambda x,y: dict(x, **y),
        [check_cpu(), check_mem(), check_zombie_process(), check_single_process()]
        )
    for func, func_result in check_result.items():
        if func_result['status'] != 'OK':
            send_mail(func + '报警',json.dumps(func_result))
            break
    write_log(json.dumps(check_result))
    print("总程序执行时间：%.3fs" % (time.time()-start_time))