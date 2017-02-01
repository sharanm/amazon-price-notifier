
import json
import requests
import subprocess
import sys
import argparse
import datetime

VRL_JOB_PREFIX = "http://ausvrl.nvidia.com/showjob.php?job="

class Job:
	def __init__(self, jobId, os, cpu, module):
		self.os = os
		self.cpu = cpu
		self.id = jobId
		self.link = VRL_JOB_PREFIX + jobId
		self.module = module
		self.branch = None

	def getBuildURL(self):
		manifestData = requests.get('http://ausvrldsk.nvidia.com/jobs/{}/{}/manifest.csv'.format(self.id[:6], self.id)).text
		manifestData = manifestData.split(",")
		for param in manifestData:
			if param.startswith("http") and (param.endswith("tgz") or param.endswith("zip")):
				return param

		raise Exception("Build not found")

	def getBuild(self):
		url = self.getBuildURL()
		build = url.replace("sanity_output.tgz", "tests_output.tbz2")
		out = subprocess.check_output("wget {}".format(build), shell=True)
		return build

def filterJobs(jobs, os=None, cpu=None, module=None):
	"""
	Filter job list based on input parameter
	"""
	jobList = []
	moduleParsed = []

	for job in jobs:

		if not os or os == job.os:
			if not cpu or cpu == job.cpu:
				if (not module or job.module.endswith(module)) and job.module not in moduleParsed:
					jobList.append(job)
					moduleParsed.append(job.module)

	return jobList

def _getSubmissionString():
	currentTime = datetime.datetime.now()
	delta = datetime.timedelta(days=2)
	cutoffTime = currentTime - delta

	def getDateString(time):
		return "%s-%02d-%02d" % (time.year, time.month, time.day)

	return "submitted:[{}* TO {}*]".format(getDateString(cutoffTime), getDateString(currentTime))


def getOlderJobs(*args, **kwargs):
	"""
	Get list of successful jobs from tintin
	"""
	query = "{}".format(_getSubmissionString())

	if kwargs["getPassingJobsOnly"]:
		query += " AND automatic AND 100"

	for value in args:
		if value:
			query += " AND {}".format(value)

	print "Tintin query : {}".format(query)

	url = "http://tintin/ajax?response=json&query={}&searchby=recent&searchopt=and".format(query)
	print url
	tintinOutput = requests.get(url)
	jobs = json.loads(tintinOutput.text).get("aaData")

	jobList = []

	for job in jobs:
		jobList.append(Job(job[0], job[10], job[9], job[8]))

	return jobList


def dumpToFile(triggeredJobs):

	with open("out", "w") as output:
	    for job in triggeredJobs:

	    	for key, value in job.items():
	        	output.write("{}: {}\t".format(key, value))

	        output.write("\n")

def triggerJobs(jobs, machine, onlyDisplay=False):


	for job in jobs:

		command = "vrlsubmit -s ausvrl -u smundhada -z {build} -o {os} -t {module}_stage -c {cpu} -n 'Older job link: {link}'".format(
																											build=job.getBuildURL(),
																											module=job.module,
																											os=job.os,
																											cpu=job.cpu,
																											link=job.link)

		if machine:
			command += " -m {}".format(machine)

		if not onlyDisplay:
			try:
				out = subprocess.check_output(command, shell=True)
				newJobLink = out.replace("Submission accepted as job(s) ", VRL_JOB_PREFIX)
				print "Triggered : {} ".format(newJobLink)
			except Exception, e:
				print "Error occurred while triggering job {}. Ensure that build is available".format(command)
		else:
			print command

def main(args):

	os = args.get("os")
	cpu = args.get("cpu")
	module = args.get("module")
	branch = args.get("branch")
	machine = args.get("machine")
	dryRun = args.get("dryRun")
	getBuild = args.get("getBuild")
	oldJobId = args.get("jobId")
	usePassingJobs = True
	if oldJobId:
		usePassingJobs = False
	interactive = args.get("interactive")

	jobs = getOlderJobs(os, cpu, module, branch, oldJobId, getPassingJobsOnly=usePassingJobs)
	jobs = filterJobs(jobs, os=os, cpu=cpu, module=module)

	if not jobs:
		print "No older jobs found"
		sys.exit(1)

	if getBuild:
		return jobs[-1].getBuild()

	if not dryRun:
		# trigger single job
		jobs = [jobs[-1]]
	triggerJobs(jobs, machine, onlyDisplay=interactive)


if __name__ == '__main__':


	parser = argparse.ArgumentParser(prog="goharness")


	parser.add_argument(
	        "--os",
	        dest="os",
	        action="store")

	parser.add_argument(
	        "--cpu",
	        dest="cpu",
	        help="Platform for which job should be triggered",
	        action="store")

	parser.add_argument(
	        "--module",
	        dest="module",
	        help="Test suite for which job should be triggered",
	        action="store")

	parser.add_argument(
	        "--machine",
	        dest="machine",
	        help="Machine on which job(s) should be triggered",
	        action="store")

	parser.add_argument(
	        "--branch",
	        dest="branch",
	        help="Branch to be used for build",
	        action="store")

	parser.add_argument(
	        "--dry-run",
	        dest="dryRun",
	        default=False,
	        help="If set, trigger jobs for all applicable modules",
	        action="store_true")

	parser.add_argument(
	        "--get-build",
	        dest="getBuild",
	        default=False,
	        help="If set, trigger jobs for all applicable modules",
	        action="store_true")

	parser.add_argument(
	        "--job-id",
	        dest="jobId",
	        help="Job Id whose build should be used",
	        action="store")

	parser.add_argument(
	        "--interactive",
	        dest="interactive",
	        default=False,
	        help="If set, just display vrlsubmit commands",
	        action="store_true")

	args = parser.parse_args().__dict__
	main(args)

