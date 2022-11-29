# ---IMPORTS-------------------------------------------------------------------
import os
import re
import json
import glob
import random
import string
import datetime
import argparse
import threading
from typing import Any, TextIO, Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import YoutubeDLError
# -----------------------------------------------------------------------------



# ---TYPE ALIASES--------------------------------------------------------------
Links = list[list[str]]
Settings = dict[str, Any]
Context = dict[str, Any]
# -----------------------------------------------------------------------------



# ---GLOBAL VARIABLES----------------------------------------------------------
all_links: Links = []
output: list[str] = []
settings: Settings = {}
loading: bool = True
# -----------------------------------------------------------------------------



# ---UTILITY FUNCTIONS---------------------------------------------------------
def resolve_path(filename: str) -> str:
	"""
	Returns the Resolved Path (Path from install location).

	Args:
		filename (str): Name of the file.

	Returns:
		str: The Resolved Path 
	"""
	# Gets the Path of the install location
	path: str = os.path.dirname(os.path.realpath(__file__))
	return os.path.join(path, filename)


def parse_links(filepath: str) -> Links:
	"""
	Parse the links from the file.

	Args:
		filepath (str): Path to the source file.
	"""
	with open(filepath, 'r') as file:
		return list(map(lambda x:[x,''], file.read().split('\n')))


def print_output() -> None:
	"""
	Prints the download status.
	"""
	ext: str = 'm4a' if settings['novideo'] else 'mkv'
	downloaded: int = len(list(map(lambda x: os.path.split(x)[1], glob.glob(settings['destination'] + '*.' + ext))))
	print("\033c", end="")  # Clears the console 
	print(f"Completed: {downloaded}\n")
	print(''.join(output))
# -----------------------------------------------------------------------------



# ---LOGGER--------------------------------------------------------------------
class CustomLogger:
	"""
	The Logger that is passed to youtube_dl for logging.
	"""
	def __init__(self) -> None:
		"""
		Custom Logger that logs the actual output from YoutubeDL
		"""
		self.log_file: TextIO = open(resolve_path('log.txt'), 'a+')
		self.log_file.truncate(0)

	def debug(self, msg: str) -> None:
		"""
		Writes the Debug Log

		Args:
			msg (str): The log message
		"""
		# Checking for ETA to avoid writing progress to the logs
		if 'ETA' not in msg:
			self.log_file.write(msg + '\n')

	def warning(self, msg: str) -> None:
		"""
		Writes the warning Log

		Args:
			msg (str): The log message
		"""
		self.log_file.write(msg + '\n')

	def error(self, msg: str) -> None:
		"""
		Writes the error Log

		Args:
			msg (str): The log message
		"""
		self.log_file.write(msg + '\n')

logger: CustomLogger = CustomLogger()
# -----------------------------------------------------------------------------



# ---MAIN CLASS----------------------------------------------------------------
class Downloader:
	"""
	The simple wrapper around youtube_dl to download videos from youtube and other sites.
		
	CommandLine Flags:-
	--start - Start Downloading
	--config - Modify config file
	-a --novideo - Downloads only audio
	-r --res - Resolution of the Video.
	-s --source - Path to link file
	-d --destination - Path to destination folder
	--nosub - Disable subtitles
	--pp - Assigns random filename
	"""
	global logger, settings

	def __init__(self, links: Links, pos: int) -> None:
		"""
		Prepare the downloader with the settings.

		Args:
			links (Links): The settings for downloading.
			pos (int): The position of output		
		"""
		self.links: list = list(map(lambda x: x[0], links))
		self.pos: int = pos
		self.current: int = 0
		self.total: int = len(all_links)

		self.context: Context = {
			'format': self._select_format(),
			'ignoreerrors': True,
			'outtmpl': settings['destination'] + self._generate_name(),
			'writesubtitles': self._set_subs(),
			'writeautomaticsub': self._set_subs(),
			'merge_output_format': 'mp4',
			'sleep_interval': 5,
			'max_sleep_interval': 25,
			'fixup': 'detect_or_warn',
			'logger': logger,
			'quiet': False,
			'progress_hooks': [self._my_hook],
		}

		# Skips postprocessing for audio
		if not settings['novideo']:
			self.context['postprocessors'] = [
					{
						'key': 'FFmpegVideoConvertor',
						'preferedformat': settings['format'],
					}, 
					{
						'key': 'FFmpegSubtitlesConvertor',
						'format': 'srt',
					},
					{
						'key': 'FFmpegEmbedSubtitle'
					}
				]


	def _my_hook(self, e: dict[str, Any]) -> None:
		"""
		Custom hook to display a different output while downloading.

		Args:
			e (dict[str, Any]): The object passed by the progress hook
		"""
		if e['status'] == 'downloading':
			# Sanitizing the data for output
			filename: str = re.sub(settings['destination'], '', e['filename'])
			short_filename: str = filename if len(filename) < 25 else filename[:25] + '...' + filename[filename.rindex('.')-5:]
			eta: str = self._parse_time(datetime.timedelta(seconds=round(e.get('eta') or 0)))
			size: float = round((e.get('total_bytes') or e.get('total_bytes_estimate') or -1000000) / 1000000, 2)
			downloaded: int = round(e['downloaded_bytes'] / 1000000, 2)
			speed: float = round((e.get('speed') or 0) / 1000000, 2)
			progress: float = round(downloaded/size * 100, 2)

			self._map_filename(filename)
			
			output[self.pos] = (f"{short_filename.ljust(12)}\t\t{'Done' if progress == 100 else str(progress) + '%'}\n{downloaded} / {size} MB | {speed} MB/s\n{eta}\n\n")

			print_output()


	def _map_filename(self, filename):
		"""
		Maps the filename with it's respective link

		Args:
			filename (str): name of the downloading file.
		"""
		ext: str = 'm4a' if settings['novideo'] else 'mp4'

		if len(self.links) > self.current:
				for i, link in enumerate(all_links):
					# If filename is already defined we can ignore it
					if link[1]: continue
					if link[0] == self.links[self.current]:
						all_links[i][1] = f"{filename.rsplit('.', 2)[0]}.{ext}"
						self.current += 1
						break


	def _parse_time(self, time: datetime.timedelta) -> str:
		out: str = ''
		if time:
			hours, minutes, seconds = list(map(lambda x: int(x), str(time).split(':')))
			if hours: out = out + f"{hours} hour{'s' if hours > 1 else ''} "
			if minutes: out = out + f"{minutes} minute{'s' if minutes > 1 else ''} "
			if seconds: out = out + f"{seconds} second{'s' if seconds > 1 else ''} "
		return out + 'left' if out else ''


	def _select_format(self) -> str:
		"""
		Returns the download format.

		Returns:
			str: The youtube_dl format to use for downloading
		"""
		if settings['novideo']:
			return "bestaudio[acodec^=opus][ext=m4a]/bestaudio[acodec^=mp4a][ext=m4a]"

		else:
			resolutions: dict[str, int] = {
				'144p': 144,
				'240p': 240,
				'360p': 360,
				'480p': 480,
				'720p': 720,
				'1080p': 1080,
				'1440p': 1440,
				'4k': 2160
			}
			res: int = resolutions[settings['res']]

			return f"(bestvideo[vcodec^=av01][height<={res}][fps>30]/bestvideo[vcodec^=vp9.2][height<={res}][fps>30]/bestvideo[vcodec^=vp9][height<={res}][fps>30]/bestvideo[vcodec^=avc1][height<={res}][fps>30]/bestvideo[height<={res}][fps>30]/bestvideo[vcodec^=av01][height<={res}]/bestvideo[vcodec^=vp9.2][height<={res}]/bestvideo[vcodec^=vp9][height<={res}]/bestvideo[vcodec^=avc1][height<={res}]/bestvideo[height<={res}])+(bestaudio[acodec^=opus]/bestaudio)/best[height<={res}]"

	
	def _set_subs(self, no_sub: bool = False) -> bool:
		"""
		Returns whether subs are required

		Args:
			no_sub (bool, optional): Ignores Subs. Defaults to False.

		Returns:
			bool: whether subs are required or not
		"""
		if no_sub: return False
		return True if not settings['novideo'] else False


	def _generate_name(self) -> str:
		"""
		Returns a randomly generated name for files

		Returns:
			str: Random file name
		"""
		if settings['pp']:
			chars: str = string.ascii_letters + string.digits
			return f".{''.join(random.choices(chars, k=10))}.%(ext)s"
		else:
			return '%(title)s.%(ext)s'


	def start(self) -> None:
		"""
		The main function that starts the download.
		"""
		ytdl = YoutubeDL(self.context)
		ytdl.download(self.links)
# -----------------------------------------------------------------------------



# ---MAIN FUNCTIONS------------------------------------------------------------
def config(options: argparse.Namespace) -> Optional[Settings]:
	"""
	Loads the settings from the config file or updates the config file if --config flag is provided

	Args:
		options(argparse.Namespace): The flags provided when executing the program

	Returns:
		Settings(optional): The config for downloading
	"""

	with open(resolve_path('config.json'), 'r+') as file:
		config: Settings = json.load(file)
		# These configs are updated in the config file
		config['res'] = options.res or config['res']
		config['source'] = options.source or config['source']
		config['destination'] = options.destination or config['destination']
		config['threads'] = options.threads or config['threads']
		config['novideo'] = options.novideo or config['novideo']
		config['format'] = options.format or config['format']

		# If --config file is provided the config is written to the file and returned
		if options.config:
			file.seek(0)
			file.truncate(0)
			json.dump(config, file, indent=4)
			return None

		# These are temporary flags that are not written in the config file.
		config['nosub'] = options.nosub
		config['pp'] = options.pp

		return config


def main() -> None:
	"""
	Main function that sets up and executes the program
	"""
	global settings
	global all_links

	parser: argparse.ArgumentParser = argparse.ArgumentParser(allow_abbrev=False, prog="tuber", usage="%(prog)s [options] --start", description="A Simple youtube_dl wrapper to download videos and music.")

	parser.add_argument('--start', action='store_true', help="Starts downloading the files")
	parser.add_argument('--config', action='store_true', help="Modify the config file")
	parser.add_argument('-r', '--res', action='store', type=str, choices=['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '4k'], help='Sets the download resolution')
	parser.add_argument('-s', '--source', action='store', type=str,help='Source File Path')
	parser.add_argument('-d', '--destination', action='store', type=str, help='Destination Path')
	parser.add_argument('-t', '--threads', action='store', type=int, help='Number of Threads (Parallel Downloads)')
	parser.add_argument('-f', '--format', action='store', type=str, help='Download format')
	parser.add_argument('-p', '--pp', action='store_true', help='Store the file with random name')
	parser.add_argument('--nosub', action='store_true', help="Disables Subtitles")
	parser.add_argument('-a', '--novideo', action='store_true', help="Downloads only audio")


	args: argparse.Namespace = parser.parse_args()	

	if args.start and not args.config:
		settings = config(args)
		all_links = parse_links(settings['source'])
		run()
		end()
	elif not args.start and args.config:
		config(args)
		print('Config updated successfully!')
	elif args.start and args.config:
		print("Error: Invalid Command.\nCan't start and config at the same time\nType tuber -h for help.")
		return
	else:
		print("Error: Invalid Command.\nType 'tuber --start' to start downloading\nType tuber -h for help.")
		return


def run() -> None:
	"""
	Initiates the downloads by creating and starting multiple threads for parallel downloads.
	"""
	global output
	global settings
	global all_links

	threads: list[threading.Thread] = []
	for x in range(settings['threads']):
		# Spliting the links to make it easier for parallel downloading.
		dl: Downloader = Downloader(all_links[x::settings['threads']], x)
		thread: threading.Thread = threading.Thread(target=dl.start)
		threads.append(thread)
		# Populating the output based on No.of threads.
		output.append('')

	# Starts all threads
	for thread in threads:
		thread.start()

	# Waits for all threads to complete the download
	for thread in threads:
		thread.join()


def end() -> None:
	"""
	End the Program and writes the failed links to a file
	"""

	global settings
	global all_links

	logger.log_file.close()

	ext: str = 'm4a' if settings['novideo'] else 'mp4'
	downloaded: list = list(map(lambda x: os.path.split(x)[1], glob.glob(settings['destination'] + '*.' + ext)))
	failed: list = list(filter(lambda x: x[1] not in downloaded, all_links))

	print("\033c", end="")

	# Checking using length since pre downloaded files are still considered as failed.
	if len(downloaded) == len(all_links): 
		print('Download Complete!')
	else:
		with open(os.path.join(settings['destination'],'failed.txt'), 'a') as file:
			file.seek(0)
			file.truncate(0)
			for link in failed:
				file.write(link[0] + '\n')
			print("\nDownload Failed!\nCheck 'failed.txt' for failed links.")

	print(f'\nCompleted: {len(downloaded)}/{len(all_links)}')
	print(f'Failed: {len(failed)}/{len(all_links)}')
#------------------------------------------------------------------------------



# ---EXECUTION-----------------------------------------------------------------
if __name__ == "__main__":
	try:
		main()
	except YoutubeDLError:
		end()
#------------------------------------------------------------------------------ 




