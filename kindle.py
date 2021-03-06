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
		sqlCommand = "select price, date from bookprice as d, (select max(date) as foo from bookprice where id='{}' group by datetime(date, 'start of day')) as f where d.date=f.foo;".format(book.id)
		output = execute(sqlCommand)
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
			if change > 10:
				pushMessage(book.name,
							message = "{}: from {} to {} \nChange of {:0.2f} %".format(
									  message, previousPrice, currentPrice, change),
							file=plot(book))

def getTweepy():
	import tweepy
	consumer_key = 'ujHhyrVsHNwBe72nCTX3l6YVN'
	consumer_secret = 'vBxsNjNmMWFbkMrKrwMe7tPlbpBP7EgMAytFJD9biRFnN0OXYg'
	access_token = '906104910457954304-pZhFx583P6FYPGzpjap0cOB6Vmu1Lv0'
	access_token_secret = '254er1OZtOhwNbSzw4mOiru6SqprOmGNKoYPpwPP61plW'
	auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
	auth.set_access_token(access_token, access_token_secret)
	api = tweepy.API(auth)
	return api

def formatTweet(title, message):
	if len(title + message) > 160:
		logger.debug("Shortening this message to 140 chars: {} {}".format(title, message))

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

def pushMessage(title, message="", file=None):
	logger.info("{}\n{}".format(title, message))
	#pushBullet(title, message)
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

def createTable():
	conn = sqlite3.connect("main.db")
	conn.execute('''CREATE TABLE if not exists BookInfo
         (ID TEXT PRIMARY KEY UNIQUE,
         NAME           TEXT,
         ADDRESS        TEXT,
	DATE		TEXT);''')

	conn.execute('''CREATE TABLE if not exists BookPrice
         (ID TEXT KEY,
         Date           TEXT,
         Price        REAL);''')

	conn.close()

def insertBookInfo(id, name, address, date):
	name = name.replace("'", "")
	query = "INSERT or REPLACE INTO BookInfo (ID, NAME, ADDRESS, DATE) VALUES ('{}', '{}', '{}', '{}');".format(id, name, address, date)
	execute(query)

def insertBookPrice(id, price, date):
	price = price.replace(",", "")
	query = "INSERT or ignore INTO BookPrice (ID,price,date)  VALUES ('{}', '{}', '{}');".format(id, price, date)
	execute(query)

def execute(query):
	try:
		conn = sqlite3.connect("main.db")
		output = [i for i in conn.execute(query)]
		conn.commit()
		return output
	except Exception, e:
		logger.exception("Query '{}' resulted in exception {}".format(query, e))
	finally:
		conn.close()

@click.group()
def cli():
    pass

def pruneList():
	output = execute("select id, name from BookInfo;")
	for (id, name) in output:
		output = execute("select date from BookInfo where id = '{}' order by datetime(date) DESC LIMIT 1;".format(id))
		if output:
			[(previousDate, )] = output
			previousDate = datetime.datetime.strptime(previousDate, "%Y-%m-%d %H:%M:%S.%f")
			if datetime.datetime.now() - previousDate > datetime.timedelta(days=5):
				logger.info("Removing the book {}".format(name))
				execute("delete from BookInfo where id = '{}'".format(id))

@cli.command()
def readList():
	address = "https://www.amazon.in/gp/registry/wishlist/?ie=UTF8&cid=A3RDF2FMSIRJOT"
	soup = BeautifulSoup(urllib.urlopen(address).read(), "lxml")
	books = soup.findAll("a", {'class': "a-link-normal"})

	if not books:
		pushMessage("No book found. Wishlist parsing logic needs an update !!")

	random.shuffle(books)

	for book in books:
		if book.get("href") and book.get("title"):
			bookAddress = "{0}{1}".format("https://www.amazon.in/", book["href"])
			book = getBookInfo(bookAddress)
			if book:
				insertBookInfo(book.id, book.name, book.address, datetime.datetime.now())
				logger.debug("{} {} {}".format(book.id, book.name, book.address))
	#pruneList()

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

def messages():
	tweepy = getTweepy()
	statuses = tweepy.home_timeline(count=1)
	for status in statuses:
		print status.text, status.id

if __name__ == '__main__':
	createTable()
	#readList()
	#tweet("foo\n"*80, "bar")
	#tweet("foocar\n", "@sharanmh31")
	#textToImage("foo\nbar")
	#notify()
	#addattr.id = '8e0e78a1a569d44d964f3052151d762f'; addattr.name = "Foo"; plot(addattr)
	#addattr.id = '34516a8862f0c841608e4ef1b350d543'; addattr.price = "20"; addattr.name = "Foo"; notifyIfChange(addattr)
	#print pushMessage("Past prices", file=plot(addattr))
	#print formatTweet("The Daily Stoic: 366 Meditations on Wisdom, Perseverance, and the Art of Living:"
	#					 "Featuring new translations of Seneca, Epictetus, and Marcus Aurelius",
    #				 "Price fall: from 341.32 to 315.4")
	#print formatTime("2017-08-31 15:10:43.275887")
	#pushMessage("foo", "car")
	#messages()
	#insertBookPrice("bdc6d832e1a4fe2d7414f9e493b9408e", "1,490.99", datetime.datetime.now())
	cli()

