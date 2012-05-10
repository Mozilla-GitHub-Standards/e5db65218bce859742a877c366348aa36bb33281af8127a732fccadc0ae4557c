import shutil
import argparse
import logging
import feedparser
import sys
import shelve
import os
import datetime

from mako.template import Template


logger = logging.getLogger('jenkins-publisher')

DB = 'jenkins.db'
TARGET_DIR = '/tmp/dashboard'

LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG}

LOG_FMT = r"%(asctime)s [%(process)d] [%(levelname)s] %(message)s"
LOG_DATE_FMT = r"%Y-%m-%d %H:%M:%S"
_MEDIUM = ('ok.png', 'fail.png')


def generate_dashboard(jobs):
    here = os.path.dirname(__file__)

    if not os.path.isdir(TARGET_DIR):
        print('%r does not seem to be a directory' % TARGET_DIR)
        sys.exit(1)

    # copying the media
    for media in _MEDIUM:
        origin = os.path.join(here, media)
        target = os.path.join(TARGET_DIR, media)
        if os.path.exists(target):
            continue
        shutil.copyfile(origin, target)

    # generating the dashboard
    with open(os.path.join(here, 'dashboard.html')) as f:
        tpl = f.read()

    res = Template(tpl).render(jobs=jobs)

    filename = os.path.join(TARGET_DIR, 'index.html')
    with open(filename, 'w') as f:
        f.write(res)

    print('Dashboard generated at %r' % filename)


def close_on_exec(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    flags |= fcntl.FD_CLOEXEC
    fcntl.fcntl(fd, fcntl.F_SETFD, flags)


def str2datetime(data):
    return datetime.datetime.strptime(data, '%Y-%m-%dT%H:%M:%SZ')


def main():
    parser = argparse.ArgumentParser(description='Reads Jenkins RSS')
    parser.add_argument('rss', help='RSS url')

    parser.add_argument('--log-level', dest='loglevel', default='info',
            help="log level")
    parser.add_argument('--log-output', dest='logoutput', default='-',
            help="log output")
    args = parser.parse_args()

    # configure the logger
    loglevel = LOG_LEVELS.get(args.loglevel.lower(), logging.INFO)
    logger.setLevel(loglevel)
    if args.logoutput == "-":
        h = logging.StreamHandler()
    else:
        h = logging.FileHandler(args.logoutput)
        close_on_exec(h.stream.fileno())
    fmt = logging.Formatter(LOG_FMT, LOG_DATE_FMT)
    h.setFormatter(fmt)
    logger.addHandler(h)
    db = shelve.open(DB)

    now = datetime.datetime.now()

    # read the feed and update the DB.
    # we just keep one entry per job
    feed = feedparser.parse(args.rss)
    for entry in feed['entries']:
        updated = entry['updated']
        job, build_id, desc = entry['title'].split(' ', 2)
        link = entry['link']
        key = '%s:::%s' % (updated, job)
        ok = desc == '(stable)'
        updated = str2datetime(updated)
        age = now - updated
        old = age.days > 0

        db[job] = {'updated': updated.strftime('%Y-%m-%d %H:%M:%S'),
                   'job': job,
                   'build_id': build_id,
                   'desc': desc,
                   'link': link,
                   'ok': ok,
                   'old': old,
                   '_updated': updated}


    # now we can generate the dashboard
    jobs = [(job['_updated'], job) for job in db.values()]
    jobs.sort()     # gets sorted by update
    jobs.reverse()
    db.close()
    generate_dashboard([job for updated, job in jobs])
    sys.exit(0)


if __name__ == '__main__':
    main()
