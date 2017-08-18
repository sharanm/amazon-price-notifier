import click
import datetime
from bs4 import BeautifulSoup
import urllib
import random
import time
import hashlib
import sqlite3


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

def notify(book):
	previousPrice = execute("SELECT price from BookPrice where id = '{}' order by datetime(date) DESC LIMIT 1;".format(book.id))
	if previousPrice:
		[(previousPrice, )] = previousPrice

		previousPrice = float(previousPrice)
		currentPrice = float(book.price)

		if currentPrice != previousPrice:
			logger.info("Notifying price change for {}".format(book.name))

			if currentPrice < previousPrice:
				message = "Price fall"
			else:
				message = "Price rise"

			change = (abs(currentPrice - previousPrice) * 100 )/previousPrice
			if change > 10:
				pushMessage(book.name, "{}: from {} to {} \nChange of {:0.2f} %".format(
						message, previousPrice, currentPrice, change))

def textToImage(text):
	from PIL import Image, ImageDraw
	img = Image.new('RGB', (400, 400))
	d = ImageDraw.Draw(img)

	y, x = 0, 0
	for line in text.splitlines():
		d.text((x,y), line, fill=(255, 0, 0))
		y = y + 10

	img.save("foo.png")
	return "foo.png"

def tweet(title, message):
	import tweepy
	consumer_key = 'ipwbeVvBGXzaRr29nhmJSWvhD'
	consumer_secret = 'hQ7u5MSJ9rSzYAlHVmGO3xF3YyxHg5o1nMSGj3CSiAA0UFNv8m'
	access_token = '1010659086-wk48LIpu3PCghvnckTCjm01QrautNkr3B5VeOyZ'
	access_token_secret = '5tJM0aSJenAaqMplSOYZM83UHMNtIhJXRTUfxGZx7CVQP'
	auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
	auth.set_access_token(access_token, access_token_secret)
	api = tweepy.API(auth)

	if len(title + message) < 160:
		# prioritize message over title
		if len(title) > 130 - len(message):
			title = title[0: 130 - len(message)] + "..."
		api.update_status("{}\n{}".format(title, message))
	else:
		message = "{}\n{}".format(title, message)
		img = textToImage(message)
		api.update_with_media(img, status="Img")

def pushMessage(title, message):
	try:
		from pushbullet.pushbullet import PushBullet
		apiKey = "o.mKznlsIJB18uq6qArGrl2AOPU2KbISsR"
		p = PushBullet(apiKey)
		# Get a list of devices
		devices = p.getDevices()
		p.pushNote(devices[0]["iden"], title, message)
		tweet(title, message)
	except Exception, e:
		logger.exception(e)

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
			notify(book)
			insertBookPrice(book.id, book.price, datetime.datetime.now())
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
	#tweet("foo\nfoo", "bar")
	#textToImage("foo\nbar")
	cli()

