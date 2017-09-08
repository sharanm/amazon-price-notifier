import click
import datetime
from bs4 import BeautifulSoup
import urllib
import random
import time
import hashlib
import sqlite3
import subprocess


import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(lineno)d (%(funcName)s) - %(message)s')

handler = logging.FileHandler('kindle_info.log')
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)

handler = logging.FileHandler('kindle_debug.log')
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)

logging.getLogger("urllib").setLevel(logging.WARNING)

def addattr():
	pass

def formatTime(timeStr):
	timeObj = datetime.datetime.strptime(timeStr, "%Y-%m-%d %H:%M:%S.%f")
	return "{}-{}-{}-{}".format(timeObj.hour, timeObj.day, timeObj.month, timeObj.year)

def plot(book):
	try:
		output = execute("select price, min(date) from bookprice where id='{}' group by price order by price ASC LIMIT 15;".format(book.id))
		picName = "prices.png"
		dataFile = "datafile.dat"
		with open(dataFile, "w") as d:
			for (price, date) in output:
				d.write("{} {}\n".format(formatTime(date), price))

		command = """gnuplot -e "filename='{}'; datafile='{}'; myTitle='Past prices'" plots""".format(picName, dataFile, book.name)
		out = subprocess.check_output(command, shell=True)
		return picName
	except Exception,e:
		logger.exception(e)
		logger.error("Error while plotting the image: {}".format(command))

def notifyIfChange(book):
	output = execute("SELECT price from BookPrice where id = '{}' order by datetime(date) DESC LIMIT 2;".format(book.id))
	if output:
		(currentPrice, ) = output[0]
		(previousPrice, ) = output[1]

		previousPrice = float(previousPrice)
		currentPrice = float(currentPrice)

		if currentPrice != previousPrice:
			if currentPrice < previousPrice:
				message = "Price fall"
			else:
				message = "Price rise"

			change = (abs(currentPrice - previousPrice) * 100 )/previousPrice
			logger.info("Price change of {} seen for {}\n".format(change, book.name))
			if change > 5:
				pushMessage(book.name,
							message = "{}: from {} to {} \nChange of {:0.2f} %".format(
									  message, previousPrice, currentPrice, change),
							file=plot(book))

def getTweepy():
	import tweepy
	consumer_key = 'ujHhyrVsHNwBe72nCTX3l6YVN'
	consumer_secret = 'vBxsNjNmMWFbkMrKrwMe7tPlbpBP7EgMAytFJD9biRFnN0OXYg'
	access_token = '906104910457954304-KiXp8RvAqEIyliWC4CGMhyXlvWwGZKi'
	access_token_secret = '1qPnFjpxl39vWJxvFigkFBXpRFXgi3yWG1gwLtk70krUO'
	auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
	auth.set_access_token(access_token, access_token_secret)
	api = tweepy.API(auth)
	return api

def formatTweet(title, message):
	if len(title + message) > 160:
		raise Exception("Can't tweet more than 140 chars {}".format(title+message))

	# prioritize message over title
	if len(title) > 130 - len(message):
		title = title[0: 130 - len(message)] + "..."

	return "{}\n{}".format(title, message)

def tweet(title, message, file=None):
	try:
		api = getTweepy()

		status = formatTweet(title, message)
		if file:
			api.update_with_media(file, status)
		else:
			api.update_status(status)

	except Exception, e:
		logger.exception(e)

def pushBullet(title, message):
	try:
		from pushbullet.pushbullet import PushBullet
		apiKey = "o.mKznlsIJB18uq6qArGrl2AOPU2KbISsR"
		p = PushBullet(apiKey)
		devices = p.getDevices()
		p.pushNote(devices[0]["iden"], title, message)
	except Exception, e:
		logger.exception(e)

def pushMessage(title, message=None, file=None):
	logger.info("{}\n{}".format(title, message))
	pushBullet(title, message)
	tweet(title, message, file)

class Book:
	def __init__(self, name, price, address):
		self.name = name
		self.id = hashlib.md5(name).hexdigest()
		self.address = address
		self.price = price

def getBookInfo(address):
	soup = BeautifulSoup(urllib.urlopen(address).read(), "lxml")

	try:
		title = soup.findAll("title")[0].get_text().encode('utf-8')
		title = title.split("eBook:")
		bookName, author = title[0], title[1].split(":")[0]
		bookName = bookName.strip()
		author = author.strip()

		ebookPriceElement = soup.findAll('tr', {'class': "kindle-price"})[0]
		priceText = ebookPriceElement.get_text().encode('utf-8')
		price = priceText.split()[3].strip()
		return Book(bookName, price, address)
	except IndexError, e:
		time.sleep(400)
		logger.debug(e)
	except Exception, e:
		logger.exception(e)

def addBookInfoToDb(bookAddress):
	book = getBookInfo(bookAddress)
	if book:
		insertBookInfo(book.id, book.name, book.address)
		logger.debug("{} {} {}".format(book.id, book.name, book.address))

def createTable():
	conn = sqlite3.connect("main.db")
	conn.execute('''CREATE TABLE if not exists BookInfo
         (ID TEXT PRIMARY KEY UNIQUE,
         NAME           TEXT,
         ADDRESS        TEXT);''')

	conn.execute('''CREATE TABLE if not exists BookPrice
         (ID TEXT KEY,
         Date           TEXT,
         Price        REAL);''')

	conn.close()

def insertBookInfo(id, name, address):
	name = name.replace("'", "")
	query = "INSERT or ignore INTO BookInfo (ID, NAME, ADDRESS) VALUES ('{}', '{}', '{}');".format(id, name, address)
	execute(query)

def insertBookPrice(id, price, date):
	query = "INSERT or ignore INTO BookPrice (ID,price,date)  VALUES ('{}', {}, '{}');".format(id, price, date)
	execute(query)

def execute(query):
	try:
		conn = sqlite3.connect("main.db")
		output = [i for i in conn.execute(query)]
		conn.commit()
		return output
	except Exception, e:
		logger.exception(e)
	finally:
		conn.close()

@click.group()
def cli():
    pass

def pruneList():
	output = execute("select id, name from BookInfo;")
	for (id, name) in output:
		output = execute("select date from BookPrice where id = '{}' order by datetime(date) DESC LIMIT 1;".format(id))
		if output:
			[(previousDate, )] = output
			previousDate = datetime.datetime.strptime(previousDate, "%Y-%m-%d %H:%M:%S.%f")
			if datetime.datetime.now() - previousDate > datetime.timedelta(days=2):
				logger.info("Removing the book {}".format(name))
				execute("delete from BookInfo where id = '{}'".format(id))

@cli.command()
def readList():
	address = "https://www.amazon.in/gp/registry/wishlist/?ie=UTF8&cid=A3RDF2FMSIRJOT"
	soup = BeautifulSoup(urllib.urlopen(address).read(), "lxml")
	books = soup.findAll('span', {'class': "a-button a-button-seebuying"})
	random.shuffle(books)
	for book in books:
		bookAddress = "{0}{1}".format("https://www.amazon.in/", book.find("a")["href"])
		addBookInfoToDb(bookAddress)
	pruneList()

@cli.command()
def updatePrices():
	conn = sqlite3.connect("main.db")
	output = execute("SELECT address from BookInfo;")
	for (address, ) in output:
		book = getBookInfo(address)
		if book:
			insertBookPrice(book.id, book.price, datetime.datetime.now())
			notifyIfChange(book)
			logger.debug("{} {} {}".format(book.id, book.name, book.address))

@cli.command()
def notifyPrices():
	bookInfos = execute("SELECT id, name from BookInfo;")
	logger.debug("Notifying the prices")
	bookData = []
	for (id, name) in bookInfos:
		bookPrices = execute("SELECT price, date from BookPrice where id = '{}' order by datetime(date) DESC LIMIT 1;".format(id))
		for (price, date) in bookPrices:
			bookData.append("{}\nPrice: {}\nDate: {}\n--------\n".format(name, price, date))

	n = 8
	bookData = [bookData[i:i+n] for i in range(0, len(bookData), n)]

	for data in bookData:
		pushMessage("Books", "".join(data))

if __name__ == '__main__':
	createTable()
	#tweet("foo\n"*80, "bar")
	#tweet("foo\n", "@sharanmh31")
	#textToImage("foo\nbar")
	#notify()
	#addattr.id = '34516a8862f0c841608e4ef1b350d543'; addattr.name = "Foo"; plot(addattr)
	#addattr.id = '34516a8862f0c841608e4ef1b350d543'; addattr.price = "20"; addattr.name = "Foo"; notifyIfChange(addattr)
	#print pushMessage("Past prices", file=plot(addattr))
	#print formatTime("2017-08-31 15:10:43.275887")
	#pushMessage("foo", "car")
	cli()

