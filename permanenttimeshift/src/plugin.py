#####################################################
# Permanent Timeshift Plugin for Enigma2 Dreamboxes
# Coded by Homey (c) 2011
#
# Version: 1.4b(modifed for openPLi Dima73)
# Support: www.dreambox-plugins.de
#####################################################
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.ConfigList import ConfigList, ConfigListScreen
from Components.config import config, configfile, getConfigListEntry, ConfigSubsection, ConfigYesNo, ConfigInteger, ConfigSelection, NoSave
from Components.Label import Label
from Components.Language import language
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.StaticText import StaticText
from Components.SystemInfo import SystemInfo
from Components.Task import Task, Job, job_manager as JobManager
from Components.UsageConfig import preferredInstantRecordPath, defaultMoviePath
from Screens.ChoiceBox import ChoiceBox
from Screens.ChannelSelection import ChannelSelection
from Screens.InfoBar import InfoBar as InfoBarOrg
from Screens.InfoBarGenerics import NumberZap, InfoBarSeek, InfoBarNumberZap, InfoBarTimeshiftState, InfoBarInstantRecord, InfoBarChannelSelection
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Setup import SetupSummary
from Screens.Standby import Standby, TryQuitMainloop
from Screens.PVRState import TimeshiftState
from ServiceReference import ServiceReference
from Tools import Directories, ASCIItranslit, Notifications
from Tools.Directories import fileExists, copyfile, resolveFilename, SCOPE_LANGUAGE, SCOPE_PLUGINS
from Plugins.Plugin import PluginDescriptor
from RecordTimer import RecordTimer, RecordTimerEntry, parseEvent

from random import randint
from enigma import eTimer, eServiceCenter, eBackgroundFileEraser, iPlayableService, iRecordableService, iServiceInformation, eEPGCache, ePoint
from os import environ, stat as os_stat, listdir as os_listdir, link as os_link, path as os_path, remove as os_remove, system as os_system, statvfs
from time import localtime, time, gmtime, strftime
from timer import TimerEntry

import gettext
import Screens.InfoBar
import Screens.Standby

##############################
###   Multilanguage Init   ###
##############################

def localeInit():
	lang = language.getLanguage()
	environ["LANGUAGE"] = lang[:2]
	gettext.bindtextdomain("enigma2", resolveFilename(SCOPE_LANGUAGE))
	gettext.textdomain("enigma2")
	gettext.bindtextdomain("PermanentTimeshift", "%s%s" % (resolveFilename(SCOPE_PLUGINS), "Extensions/PermanentTimeshift/locale/"))

def _(txt):
	t = gettext.dgettext("PermanentTimeshift", txt)
	if t == txt:
		t = gettext.gettext(txt)
	return t

localeInit()
language.addCallback(localeInit)

##############################
#####  CONFIG SETTINGS   #####
##############################

config.plugins.pts = ConfigSubsection()
config.plugins.pts.enabled = ConfigYesNo(default = True)
config.plugins.pts.maxevents = ConfigInteger(default=5, limits=(1, 50))
config.plugins.pts.maxlength = ConfigInteger(default=180, limits=(5, 720))
config.plugins.pts.startdelay = ConfigInteger(default=5, limits=(5, 900))
config.plugins.pts.showinfobar = ConfigYesNo(default = False)
config.plugins.pts.infobar_skin = ConfigSelection([("0", _("new")),("1", _("default"))], "1")
config.plugins.pts.stopwhilerecording = ConfigYesNo(default = False)
config.plugins.pts.favoriteSaveAction = ConfigSelection([("askuser", _("Ask user")),("saveTimeshift", _("Save and stop")),("savetimeshiftandrecord", _("Save and record")),("noSave", _("Don't save"))], "askuser")
config.plugins.pts.permanentrecording = ConfigYesNo(default = False)
config.plugins.pts.isRecording = NoSave(ConfigYesNo(default = False))
config.plugins.pts.mode = ConfigSelection([("0", _("automatic (permanent)")),("1", _("manual (standart)"))], "0")
config.plugins.pts.manualmode = ConfigSelection([("0", _("pause")),("1", _("Live TV"))], "0")
choicelist = []
for i in (500, 1000, 1500, 2500, 3000, 3500, 4000, 4500, 5000):
	choicelist.append(("%d" % i, "%d ms" % i))
config.plugins.pts.manual_startdelay = ConfigSelection(default = "0", choices = [("0", _("disabled"))] + choicelist)
config.plugins.pts.length_no_epg = ConfigInteger(default=120, limits=(3, 720))
config.plugins.pts.long_stop = ConfigSelection([("setup", _("open setup")),("stop", _("stop timeshift"))], "setup")
config.plugins.pts.check_timeshift = ConfigYesNo(default = False)
config.plugins.pts.show_icon = ConfigYesNo(default = False)
config.plugins.pts.icon_mode = ConfigSelection([("0", _("blink")),("1", _("static"))], "0")
config.plugins.pts.x = ConfigInteger(default=60, limits=(0,9999))
config.plugins.pts.y = ConfigInteger(default=60, limits=(0,9999))
config.plugins.pts.z = ConfigSelection([(str(x), str(x)) for x in range(-20,21)], "-1")
config.plugins.pts.icon_color = ConfigSelection([("0", _("blue")),("1", _("white")),("2", _("clock (white)")),("3", _("red")),("4", _("maroon"))], "1")
config.plugins.pts.long_record = ConfigSelection([("record", _("start/stop instant record")),("event", _("open list timeshift event"))], "event")
config.plugins.pts.http_stream = ConfigYesNo(default = False)
config.plugins.pts.save_filetimeshift = ConfigYesNo(default = False)

###################################
###  PTS Indicator Screen  ###
###################################

from Components.Sources.Boolean import Boolean

PTSIndicatorSkin = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts.png" position="0,0" size="48,48" alphatest="on">
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkinBlink = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts.png" position="0,0" size="48,48" alphatest="on">
				<convert type="ConditionalShowHide">Blink</convert>
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkin1 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts1.png" position="0,0" size="48,48" alphatest="on">
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkinBlink1 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts1.png" position="0,0" size="48,48" alphatest="on">
				<convert type="ConditionalShowHide">Blink</convert>
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkin2 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts2.png" position="0,0" size="48,48" alphatest="on">
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkinBlink2 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts2.png" position="0,0" size="48,48" alphatest="on">
				<convert type="ConditionalShowHide">Blink</convert>
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkin3 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts3.png" position="0,0" size="48,48" alphatest="on">
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkinBlink3 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts3.png" position="0,0" size="48,48" alphatest="on">
				<convert type="ConditionalShowHide">Blink</convert>
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkin4 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts4.png" position="0,0" size="48,48" alphatest="on">
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

PTSIndicatorSkinBlink4 = """
		<screen name="PTSIndicator" title="Timeshift Indicator" flags="wfNoBorder" position="60,60" size="48,48" zPosition="%s" backgroundColor="transparent" >
			<widget source="Boolean" render="Pixmap" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/icon/ts4.png" position="0,0" size="48,48" alphatest="on">
				<convert type="ConditionalShowHide">Blink</convert>
			</widget>  
		</screen>""" % (config.plugins.pts.z.value)

class PTSIndicator(Screen):
	def __init__(self, session):
		if config.plugins.pts.icon_mode.value == "0":
			if config.plugins.pts.icon_color.value == "0":
				self.skin = PTSIndicatorSkinBlink
			elif config.plugins.pts.icon_color.value == "1":
				self.skin = PTSIndicatorSkinBlink1
			elif config.plugins.pts.icon_color.value == "2":
				self.skin = PTSIndicatorSkinBlink2
			elif config.plugins.pts.icon_color.value == "3":
				self.skin = PTSIndicatorSkinBlink3
			elif config.plugins.pts.icon_color.value == "4":
				self.skin = PTSIndicatorSkinBlink4
		else:
			if config.plugins.pts.icon_color.value == "0":
				self.skin = PTSIndicatorSkin
			elif config.plugins.pts.icon_color.value == "1":
				self.skin = PTSIndicatorSkin1
			elif config.plugins.pts.icon_color.value == "2":
				self.skin = PTSIndicatorSkin2
			elif config.plugins.pts.icon_color.value == "3":
				self.skin = PTSIndicatorSkin3
			elif config.plugins.pts.icon_color.value == "4":
				self.skin = PTSIndicatorSkin4
		Screen.__init__(self, session)
		self.skinName = ["PTSIndicator" + self.__class__.__name__, "PTSIndicator"]
		self["Boolean"] = Boolean(fixed = True)
		config.plugins.pts.x.addNotifier(self.__changePosition, False)
		config.plugins.pts.y.addNotifier(self.__changePosition, False)
		self.onLayoutFinish.append(self.__changePosition)

	def __changePosition(self, configElement=None):
		if not self.instance is None:
			self.instance.move(ePoint(config.plugins.pts.x.value,config.plugins.pts.y.value))


###################################
###  PTS TimeshiftState Screen  ###
###################################

class PTSTimeshiftState(Screen):
	if config.plugins.pts.infobar_skin.value == "0":
		skin = """
			<screen position="center,13" zPosition="2" size="420,150" backgroundColor="#ff000000" flags="wfNoBorder">
				<widget name="state" position="3,28" zPosition="2" borderWidth="2" borderColor="white" size="100,25" font="Regular;20" halign="center" foregroundColor="black" backgroundColor="background" transparent="1" />
				<widget source="session.CurrentService" render="Label" position="320,45" size="100,37" font="Regular;30" halign="center" foregroundColor="red" backgroundColor="background" transparent="1">
					<convert type="ServicePosition">Remaining</convert>
				</widget>
				<eLabel position="10,50" size="420,70" zPosition="-1" backgroundColor="background" />
				<eLabel text="Buffer:" position="105,52" size="90,20" zPosition="5" halign="right" font="Regular;20" foregroundColor="blue" backgroundColor="background" transparent="1" />
				<eLabel text="-  100%  -  90%  -  80%  -  70%  -  60%  -  50%  -  40%  -  30%  -  20%  -  10%  -  0%  -" position="9,106" size="420,12" zPosition="5" font="Regular;10" foregroundColor="white" backgroundColor="background" transparent="1" />
				<widget source="session.CurrentService" render="Label" zPosition="5" position="200,52" size="100,20" font="Regular;20" halign="center" foregroundColor="blue" backgroundColor="background" transparent="1">
					<convert type="ServicePosition">Length</convert>
				</widget>
				<widget name="PTSSeekPointer" position="158,88" zPosition="3" size="19,50" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/now/timelines_new.png" alphatest="on" />
				<ePixmap position="10,88" size="840,15" zPosition="1" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/now/slider_back.png" alphatest="on"/>
				<ePixmap position="0,0" size="100,106" zPosition="0" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/now/pts_bar.png" alphatest="on"/>
				<ePixmap position="100,40" size="200,38" zPosition="0" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/now/button_grey200.png" alphatest="on"/>
				<widget source="session.CurrentService" render="Progress" position="10,95" size="420,6" zPosition="2" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/now/slider.png" transparent="1">
					<convert type="ServicePosition">Position</convert>
				</widget>
				<widget name="eventname" position="0,122" zPosition="5" size="420,20" font="Regular;18" halign="center" foregroundColor="yellow" backgroundColor="#ff000000" />
			</screen>"""
	else:
		skin = """
			<screen position="center,40" zPosition="2" size="420,70" backgroundColor="transpBlack" flags="wfNoBorder">
				<widget name="state" position="10,3" size="80,27" font="Regular;20" halign="center" backgroundColor="transpBlack" />
				<widget source="session.CurrentService" render="Label" position="95,5" size="120,27" font="Regular;20" halign="left" foregroundColor="white" backgroundColor="transpBlack">
					<convert type="ServicePosition">Position</convert>
				</widget>
				<widget source="session.CurrentService" render="Label" position="340,5" size="65,27" font="Regular;20" halign="left" foregroundColor="white" backgroundColor="transpBlack">
					<convert type="ServicePosition">Length</convert>
				</widget>
				<widget name="PTSSeekPointer" position="8,30" zPosition="3" size="19,50" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/timeline-now.png" alphatest="on" />
				<ePixmap position="10,33" size="840,15" zPosition="1" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/slider_back.png" alphatest="on"/>
				<widget source="session.CurrentService" render="Progress" position="10,33" size="390,15" zPosition="2" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/images/slider.png" transparent="1">
					<convert type="ServicePosition">Position</convert>
				</widget>
				<widget name="eventname" position="10,49" zPosition="4" size="420,20" font="Regular;18" halign="center" backgroundColor="transpBlack" />
			</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["state"] = Label(text="")
		self["PTSSeekPointer"] = Pixmap()
		self["eventname"] = Label(text="")

###################################
###   PTS CopyTimeshift Task    ###
###################################

class CopyTimeshiftJob(Job):
	def __init__(self, toolbox, cmdline, srcfile, destfile, eventname):
		Job.__init__(self, _("Saving Timeshift files"))
		self.toolbox = toolbox
		AddCopyTimeshiftTask(self, cmdline, srcfile, destfile, eventname)

class AddCopyTimeshiftTask(Task):
	def __init__(self, job, cmdline, srcfile, destfile, eventname):
		Task.__init__(self, job, eventname)
		self.toolbox = job.toolbox
		self.setCmdline(cmdline)
		self.srcfile = config.usage.timeshift_path.value + "/" + srcfile + ".copy"
		self.destfile = destfile + ".ts"

		self.ProgressTimer = eTimer()
		self.ProgressTimer.callback.append(self.ProgressUpdate)

	def ProgressUpdate(self):
		if self.srcsize <= 0 or not fileExists(self.destfile, 'r'):
			return

		self.setProgress(int((os_path.getsize(self.destfile)/float(self.srcsize))*100))
		self.ProgressTimer.start(15000, True)

	def prepare(self):
		if fileExists(self.srcfile, 'r'):
			self.srcsize = os_path.getsize(self.srcfile)
			self.ProgressTimer.start(15000, True)

		self.toolbox.ptsFrontpanelActions("start")
		config.plugins.pts.isRecording.value = True

	def afterRun(self):
		self.setProgress(100)
		self.ProgressTimer.stop()
		self.toolbox.ptsCopyFilefinished(self.srcfile, self.destfile)

###################################
###   PTS MergeTimeshift Task   ###
###################################

class MergeTimeshiftJob(Job):
	def __init__(self, toolbox, cmdline, srcfile, destfile, eventname):
		Job.__init__(self, _("Merging Timeshift files"))
		self.toolbox = toolbox
		AddMergeTimeshiftTask(self, cmdline, srcfile, destfile, eventname)

class AddMergeTimeshiftTask(Task):
	def __init__(self, job, cmdline, srcfile, destfile, eventname):
		Task.__init__(self, job, eventname)
		self.toolbox = job.toolbox
		self.setCmdline(cmdline)
		self.srcfile = config.usage.default_path.value + "/" + srcfile
		self.destfile = config.usage.default_path.value + "/" + destfile

		self.ProgressTimer = eTimer()
		self.ProgressTimer.callback.append(self.ProgressUpdate)

	def ProgressUpdate(self):
		if self.srcsize <= 0 or not fileExists(self.destfile, 'r'):
			return

		self.setProgress(int((os_path.getsize(self.destfile)/float(self.srcsize))*100))
		self.ProgressTimer.start(7500, True)

	def prepare(self):
		if fileExists(self.srcfile, 'r') and fileExists(self.destfile, 'r'):
			fsize1 = os_path.getsize(self.srcfile)
			fsize2 = os_path.getsize(self.destfile)
			self.srcsize = fsize1 + fsize2
			self.ProgressTimer.start(7500, True)

		self.toolbox.ptsFrontpanelActions("start")
		config.plugins.pts.isRecording.value = True

	def afterRun(self):
		self.setProgress(100)
		self.ProgressTimer.stop()
		self.toolbox.ptsMergeFilefinished(self.srcfile, self.destfile)

##################################
###   Create APSC Files Task   ###
##################################

class CreateAPSCFilesJob(Job):
	def __init__(self, toolbox, cmdline, eventname):
		Job.__init__(self, _("Creating AP and SC Files"))
		self.toolbox = toolbox
		CreateAPSCFilesTask(self, cmdline, eventname)

class CreateAPSCFilesTask(Task):
	def __init__(self, job, cmdline, eventname):
		Task.__init__(self, job, eventname)
		self.toolbox = job.toolbox
		self.setCmdline(cmdline)

	def prepare(self):
		self.toolbox.ptsFrontpanelActions("start")
		config.plugins.pts.isRecording.value = True

	def afterRun(self):
		self.setProgress(100)
		self.toolbox.ptsSaveTimeshiftFinished()

###########################
#####  Class InfoBar  #####
###########################
class InfoBar(InfoBarOrg):
	def __init__(self, session):
		InfoBarOrg.__init__(self, session)
		InfoBarOrg.instance = self

		self.__event_tracker = ServiceEventTracker(screen = self, eventmap =
			{
				iPlayableService.evStart: self.__evStart,
				iPlayableService.evEnd: self.__evEnd,
				iPlayableService.evSOF: self.__evSOF,
				iPlayableService.evUpdatedInfo: self.__evInfoChanged,
				iPlayableService.evUpdatedEventInfo: self.__evEventInfoChanged,
				iPlayableService.evSeekableStatusChanged: self.__seekableStatusChangedPTS,
				#iPlayableService.evNewProgramInfo: self.__evNewProgramInfo,
				iPlayableService.evUser+1: self.ptsTimeshiftFileChanged
			})

		self["PTSactions"] = ActionMap(["PTS_GlobalActions"],{"stop2Timeshift": self.stop2Timeshift, "stopTimeshift": self.stopTimeshift, "openSetup": self.selectOptions },-1)
		self["InfobarPTSRecordactions"] = ActionMap(["InfobarPTSRecord"],{"instantRecord": self.instantRecord, "eventList": self.eventListPTS },-1)
		self["PTSSeekPointerActions"] = ActionMap(["PTS_SeekPointerActions"],{"SeekPointerOK": self.ptsSeekPointerOK, "SeekPointerLeft": self.ptsSeekPointerLeft, "SeekPointerRight": self.ptsSeekPointerRight},-2)
		self["PTSSeekPointerActions"].setEnabled(False)

		self.timeshift_enabled = False
		self.pts_begintime = 0
		self.pts_pathchecked = False
		self.pts_pvrStateDialog = "TimeshiftState"
		self.pts_seektoprevfile = False
		self.pts_switchtolive = False
		self.pts_currplaying = 1
		self.pts_lastseekspeed = 0
		self.pts_service_changed = False
		self.pts_record_running = self.session.nav.RecordTimer.isRecording()
		self.save_current_timeshift = False
		self.save_timeshift_file = False
		self.save_timeshift_postaction = None
		self.save_timeshift_filename = None
		self.timeshift_was_activated = False
		self.service_changed = False
		self.service_begintime = -1
		self.zap_postaction = False
		self.seek_action = False
		self.pts_ref = None
		self.TimeshiftIndicator = None
		config.plugins.pts.show_icon.addNotifier(self.__showHideIndicator, False)
		config.plugins.pts.enabled.addNotifier(self.__showHideIndicator, False)
		#try:
		#	config.usage.check_timeshift.addNotifier(self.__configChanged)
		#except:
		#	pass
		# Init Global Variables
		self.session.ptsmainloopvalue = 0
		config.plugins.pts.isRecording.value = False

		# Init eBackgroundFileEraser
		self.BgFileEraser = eBackgroundFileEraser.getInstance()

		# Init PTS Delay-Timer
		self.pts_delay_timer = eTimer()
		self.pts_delay_timer.callback.append(self.activatePermanentTimeshift)

		# Init PTS LengthCheck-Timer
		self.pts_LengthCheck_timer = eTimer()
		self.pts_LengthCheck_timer.callback.append(self.ptsLengthCheck)

		# Init PTS MergeRecords-Timer
		self.pts_mergeRecords_timer = eTimer()
		self.pts_mergeRecords_timer.callback.append(self.ptsMergeRecords)

		# Init PTS Merge Cleanup-Timer
		self.pts_mergeCleanUp_timer = eTimer()
		self.pts_mergeCleanUp_timer.callback.append(self.ptsMergePostCleanUp)

		# Init PTS QuitMainloop-Timer
		self.pts_QuitMainloop_timer = eTimer()
		self.pts_QuitMainloop_timer.callback.append(self.ptsTryQuitMainloop)

		# Init PTS CleanUp-Timer
		self.pts_cleanUp_timer = eTimer()
		self.pts_cleanUp_timer.callback.append(self.ptsCleanTimeshiftFolder)
		self.pts_cleanUp_timer.start(30000, True)

		# Init PTS SeekBack-Timer
		self.pts_SeekBack_timer = eTimer()
		self.pts_SeekBack_timer.callback.append(self.ptsSeekBackTimer)

		# Init Block-Zap Timer
		self.pts_blockZap_timer = eTimer()
		
		self.wait_pts = eTimer()
		self.wait_pts.timeout.get().append(self.StartManualPTS)

		# Record Event Tracker
		self.session.nav.RecordTimer.on_state_change.append(self.ptsTimerEntryStateChange)

		# Keep Current Event Info for recordings
		self.pts_eventcount = 1
		self.pts_curevent_begin = int(time())
		self.pts_curevent_end = 0
		self.pts_curevent_name = _("Timeshift")
		self.pts_curevent_description = ""
		self.pts_curevent_servicerefname = ""
		self.pts_curevent_station = ""
		self.pts_curevent_eventid = None

		# Init PTS Infobar
		self.pts_seekpointer_MinX = 8
		self.pts_seekpointer_MaxX = 396 # make sure you can divide this through 2

	def __evStart(self):
		self.service_changed = True
		self.pts_delay_timer.stop()
		self.pts_service_changed = True
		if config.plugins.pts.enabled.value:
			if config.plugins.pts.check_timeshift.value:
				try:
					config.usage.check_timeshift.setValue(True)
				except:
					pass
			else:
				try:
					config.usage.check_timeshift.setValue(False)
				except:
					pass
			self.service_begintime = -1
			self.zap_postaction = False
			self.seek_action = False
			if self.pts_ref is not None and config.plugins.pts.mode.value == "1" and not self.save_current_timeshift:
				if not self.pts_cleanUp_timer.isActive():
					self.pts_cleanUp_timer.start(5000, True)
			self.pts_ref = None

	def __showHideIndicator(self, configElement=None):
		if not config.plugins.pts.show_icon.value or not config.plugins.pts.enabled.value:
			if self.TimeshiftIndicator is not None:
				self.TimeshiftIndicator.hide()
				self.TimeshiftIndicator = None
			else:
				self.TimeshiftIndicator = None

	#def __configChanged(self, cfgElem):
	#	if config.plugins.pts.enabled.value:
	#		cfgElem.save()

	def __evEnd(self):
		self.service_changed = False
		self.service_begintime = -1
		if config.plugins.pts.enabled.value:
			if config.plugins.pts.show_icon.value:
				if self.TimeshiftIndicator is not None:
					self.TimeshiftIndicator.hide()
					if config.plugins.pts.mode.value == "1":
						self.TimeshiftIndicator = None
			else:
				self.TimeshiftIndicator = None
		self.timeshift_enabled = False

	def __evSOF(self):
		if not config.plugins.pts.enabled.value or not self.timeshift_enabled:
			return

		if self.pts_currplaying == 1:
			preptsfile = config.plugins.pts.maxevents.value
		else:
			preptsfile = self.pts_currplaying-1

		# Switch to previous TS file by seeking forward to next one
		if fileExists("%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value, preptsfile), 'r') and preptsfile != self.pts_eventcount:
			self.pts_seektoprevfile = True
			self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (preptsfile))

			self.setSeekState(self.SEEK_STATE_PAUSE)
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)
			self.doSeek(-1)
			self.seekFwd()

	def __evInfoChanged(self):
		if not config.plugins.pts.enabled.value:
			return
		if self.service_changed:
			self.service_changed = False
			# We zapped away before saving the file, save it now!
			save = self.save_current_timeshift
			if self.save_current_timeshift:
				self.SaveTimeshift("pts_livebuffer.%s" % (self.pts_eventcount))

			# Delete Timeshift Records on zap
			self.pts_eventcount = 0
			if config.plugins.pts.mode.value == "0":
				#if not self.pts_cleanUp_timer.isActive():
				self.pts_cleanUp_timer.start(3000, True)
			else:
				if save and not self.pts_cleanUp_timer.isActive():
					self.pts_cleanUp_timer.start(5000, True)
			if config.plugins.pts.mode.value == "0":
				event = None
				try:
					serviceref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
				except:
					serviceref = self.session.nav.getCurrentlyPlayingServiceReference()
				try:
					service = self.session.nav.getCurrentService()
					if serviceref is not None:
						epg = eEPGCache.getInstance()
						event = epg.lookupEventTime(serviceref, -1, 0)
					if event is None:
						info = service.info()
						ev = info.getEvent(0)
						event = ev
				except:
					pass
				if event is None:
					if self.service_begintime == -1:
						self.__evEventInfoChanged()

	def __evEventInfoChanged(self):
		if not config.plugins.pts.enabled.value:
			return
		if config.plugins.pts.mode.value == "1" and not self.timeshift_enabled:
			return
		# Get Current Event Info
		service = self.session.nav.getCurrentService()
		ts = service and service.timeshift()
		service_begin_time = self.service_begintime
		old_begin_time = self.pts_begintime
		info = service and service.info()
		ptr = info and info.getEvent(0)
		self.pts_begintime = ptr and ptr.getBeginTime() or 0
		if service_begin_time == -1 or service_begin_time != self.pts_begintime:
			self.service_begintime = self.pts_begintime
			self.seek_action = False
			if config.plugins.pts.check_timeshift.value:
				try:
					config.usage.check_timeshift.setValue(True)
				except:
					pass
			else:
				try:
					config.usage.check_timeshift.setValue(False)
				except:
					pass
		else:
			return
		start_timeshift = False
		if config.plugins.pts.http_stream.value:
			ts = service and service.timeshift()
			if ts is not None: 
				start_timeshift = True
		else:
			if info.getInfo(iServiceInformation.sVideoPID) != -1 or (config.plugins.pts.mode.value == "1" and info.getInfo(iServiceInformation.sAudioPID) != -1):
				start_timeshift = True
		# Save current TimeShift permanently now ...
		if start_timeshift:
			if config.plugins.pts.mode.value == "1":
				try:
					cur_ref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
				except:
					cur_ref = self.session.nav.getCurrentlyPlayingServiceReference()
				if cur_ref is None:
					return
				if self.pts_ref is not None and self.pts_ref == cur_ref:
					self.pts_service_changed = False
				else:
					return
			# Take care of Record Margin Time ...
			if self.save_current_timeshift and self.timeshift_enabled:
				if config.recording.margin_after.value > 0 and len(self.recording) == 0:
					self.SaveTimeshift(mergelater=True)
					recording = RecordTimerEntry(ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference()), time(), time()+(config.recording.margin_after.value*60), self.pts_curevent_name, self.pts_curevent_description, self.pts_curevent_eventid, dirname = config.usage.default_path.value)
					recording.dontSave = True
					self.session.nav.RecordTimer.record(recording)
					self.recording.append(recording)
				else:
					self.SaveTimeshift()

			# Restarting active timers after zap ...
			if self.pts_delay_timer.isActive() and not self.timeshift_enabled:
				self.pts_delay_timer.start(config.plugins.pts.startdelay.value*1000, True)
			if self.pts_cleanUp_timer.isActive() and not self.timeshift_enabled:
				self.pts_cleanUp_timer.start(3000, True)

			# (Re)Start TimeShift
			if not self.pts_delay_timer.isActive():
				if not self.timeshift_enabled or old_begin_time != self.pts_begintime or old_begin_time == 0:
					if self.pts_service_changed:
						self.pts_service_changed = False
						self.pts_delay_timer.start(config.plugins.pts.startdelay.value*1000, True)
					else:
						self.pts_delay_timer.start(100, True)

	def __seekableStatusChangedPTS(self):
		if not config.plugins.pts.enabled.value:
			return
		enabled = False
		if not self.isSeekable() and self.timeshift_enabled:
			enabled = True
		self["TimeshiftActivateActions"].setEnabled(enabled)

		enabled = False
		if config.plugins.pts.enabled.value and config.plugins.pts.showinfobar.value and self.timeshift_enabled and self.isSeekable():
			enabled = True

		self["PTSSeekPointerActions"].setEnabled(enabled)

		# Reset Seek Pointer And Eventname in InfoBar
		if config.plugins.pts.enabled.value and config.plugins.pts.showinfobar.value and self.timeshift_enabled and not self.isSeekable():
			if self.pts_pvrStateDialog == "PTSTimeshiftState":
				self.pvrStateDialog["eventname"].setText("")
			self.ptsSeekPointerReset()

		# setNextPlaybackFile() when switching back to live tv
		if config.plugins.pts.enabled.value and self.timeshift_enabled and not self.isSeekable():
			if self.pts_starttime <= (time()-5):
				self.pts_blockZap_timer.start(3000, True)
			self.pts_currplaying = self.pts_eventcount
			self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (self.pts_eventcount))
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value and not self.seek_action and self.isSeekable():
			self.seek_action = True

	def eraseFile(self, filePath):
		# We only want to use E2 Background Eraser if file has no other links on it.
		# Early Enigma2 3.20 Releases had a bug that also affected the hardlinked files.
		if fileExists(filePath):
			if os_stat(filePath).st_nlink != 1:
				os_remove(filePath)
			else:
				self.BgFileEraser.erase(filePath)

	def eraseTimeshiftFile(self):
		for filename in os_listdir(config.usage.timeshift_path.value):
			if filename.startswith("timeshift.") and not filename.endswith(".sc") and not filename.endswith(".del") and not filename.endswith(".copy"):
				self.eraseFile("%s/%s" % (config.usage.timeshift_path.value,filename))

	def activatePermanentTimeshift(self):
		if self.ptsCheckTimeshiftPath() is False or self.session.screen["Standby"].boolean is True or self.ptsLiveTVStatus() is False or (config.plugins.pts.stopwhilerecording.value and self.pts_record_running):
			return

		# Replace PVR Timeshift State Icon
		if config.plugins.pts.showinfobar.value:
			if self.pts_pvrStateDialog != "PTSTimeshiftState":
				self.pts_pvrStateDialog = "PTSTimeshiftState"
				self.pvrStateDialog = self.session.instantiateDialog(PTSTimeshiftState)
		elif not config.plugins.pts.showinfobar.value and self.pts_pvrStateDialog != "TimeshiftState":
			self.pts_pvrStateDialog = "TimeshiftState"
			self.pvrStateDialog = self.session.instantiateDialog(TimeshiftState)

		# Set next-file on event change only when watching latest timeshift ...
		if self.isSeekable() and self.pts_eventcount == self.pts_currplaying:
			pts_setnextfile = True
		else:
			pts_setnextfile = False

		# Update internal Event Counter
		if self.pts_eventcount >= config.plugins.pts.maxevents.value:
			self.pts_eventcount = 0

		self.pts_eventcount += 1

		# Do not switch back to LiveTV while timeshifting
		if self.isSeekable():
			switchToLive = False
		else:
			switchToLive = True

		# setNextPlaybackFile() on event change while timeshifting
		if self.pts_eventcount > 1 and self.isSeekable() and pts_setnextfile:
			self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (self.pts_eventcount))

		# (Re)start Timeshift now
		self.stopTimeshiftConfirmed(True, switchToLive)
		ts = self.getTimeshift()
		if ts and ts.isTimeshiftActive():
			return
		if ts and not ts.startTimeshift():
			try:
				self.save_timeshift_file = False
				self.save_timeshift_in_movie_dir = False
				self.current_timeshift_filename = ts.getTimeshiftFilename()
				self.new_timeshift_filename = self.generateNewTimeshiftFileName()
			except:
				self.current_timeshift_filename = False
			self.timeshift_enabled = True
			self.pts_starttime = time()
			self.pts_LengthCheck_timer.start(120000)
			self.save_timeshift_postaction = None
			self.ptsGetEventInfo()
			self.ptsCreateHardlink()
			self.__seekableStatusChangedPTS()
			if config.plugins.pts.mode.value == "1":
				self.activateTimeshiftEndAndPause()
				try:
					self.pts_ref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
				except:
					self.pts_ref = self.session.nav.getCurrentlyPlayingServiceReference()
				if config.plugins.pts.manualmode.value == "1":
					if self.seekstate != self.SEEK_STATE_PLAY:
						self.setSeekState(self.SEEK_STATE_PLAY)
			if config.plugins.pts.show_icon.value:
				if self.TimeshiftIndicator is None:
					self.TimeshiftIndicator = self.session.instantiateDialog(PTSIndicator)
					self.TimeshiftIndicator.show()
				else:
					self.TimeshiftIndicator.show()
		else:
			self.pts_eventcount = 0
			self.pts_ref = None
			self.seek_action = False
			
	def StartManualPTS(self):
		self.activatePermanentTimeshift()
		
	def selectOptions(self):
		if config.plugins.pts.long_stop.value =="setup":
			self.openSetup()
		else:
			self.stop2Timeshift()

	def openSetup(self):
		self.session.open(PermanentTimeShiftSetup)

	def startTimeshift(self, pauseService=True):
		if config.plugins.pts.enabled.value:
			if self.timeshift_enabled:
				return
			self.pts_delay_timer.stop()
			if config.plugins.pts.mode.value == "1":
				if not self.pts_cleanUp_timer.isActive():
					self.pts_cleanUp_timer.start(0, True)
				if not self.wait_pts.isActive():
					self.wait_pts.start(int(config.plugins.pts.manual_startdelay.value), True)
			else:
				self.activatePermanentTimeshift()
				self.activateTimeshiftEndAndPause()
		else:
			try:
				InfoBarOrg.startTimeshift(self, pauseService)
			except:
				InfoBarOrg.startTimeshift(self)

	def stop2Timeshift(self):
		if config.plugins.pts.enabled.value and self.timeshift_enabled:
			ts = self.getTimeshift()
			if ts is None:
				return
			if config.plugins.pts.mode.value == "1":
				text = _("Stop timeshift?")
			else:
				text = _("Stop Timeshift on the current channel?")
			if self.save_current_timeshift:
				text += _("\nThe Timeshift record event was not over yet!")
			self.session.openWithCallback(self.stop2TimeshiftConfirmed, MessageBox, text, MessageBox.TYPE_YESNO)

	def stopTimeshift(self):
		if config.plugins.pts.enabled.value:
			if not self.timeshift_enabled:
				return 0
			# Jump Back to Live TV
			if self.isSeekable():
				self.pts_switchtolive = True
				self.ptsSetNextPlaybackFile("")
				self.setSeekState(self.SEEK_STATE_PAUSE)
				if self.seekstate != self.SEEK_STATE_PLAY:
					self.setSeekState(self.SEEK_STATE_PLAY)
				self.doSeek(-1) # seek 1 gop before end
				self.seekFwd() # seekFwd to switch to live TV
				return 1
			return 0
		else:
			InfoBarOrg.stopTimeshift(self)

	def stop2TimeshiftConfirmed(self, confirmed, switchToLive=True):
		was_enabled = self.timeshift_enabled

		if not confirmed:
			return
		ts = self.getTimeshift()
		if ts is None:
			return
		if self.isSeekable():
			self.pts_switchtolive = True
			self.ptsSetNextPlaybackFile("")
			self.setSeekState(self.SEEK_STATE_PAUSE)
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)
			self.doSeek(-1)
			self.seekFwd() 
		# Get rid of old timeshift file before E2 truncates its filesize
		self.eraseTimeshiftFile()

		# Stop Timeshift now
		try:
			ts.stopTimeshift(switchToLive)
		except:
			ts.stopTimeshift()

		if config.plugins.pts.show_icon.value:
			if self.TimeshiftIndicator is not None:
				self.TimeshiftIndicator.hide()
		else:
			self.TimeshiftIndicator = None

		self.timeshift_enabled = False
		self.__seekableStatusChangedPTS()
		if self.save_current_timeshift and was_enabled:
			self.SaveTimeshift("pts_livebuffer.%s" % (self.pts_eventcount))
			self.pts_eventcount = 0
		if config.plugins.pts.mode.value == "1" and was_enabled:
			if not self.pts_cleanUp_timer.isActive():
				self.pts_cleanUp_timer.start(5000, True)
		self.pts_ref = None
		if was_enabled and not self.timeshift_enabled:
			self.timeshift_enabled = False
			self.pts_LengthCheck_timer.stop()

	def stopTimeshiftConfirmed(self, confirmed, switchToLive=True):
		was_enabled = self.timeshift_enabled

		if not confirmed:
			return
			
		#if config.plugins.pts.mode.value == "1" and not self.timeshift_enabled:
		#	return
		ts = self.getTimeshift()
		if ts is None:
			return

		# Get rid of old timeshift file before E2 truncates its filesize
		self.eraseTimeshiftFile()

		# Stop Timeshift now 
		try:
			ts.stopTimeshift(switchToLive)
		except:
			ts.stopTimeshift()


		self.timeshift_enabled = False
		self.__seekableStatusChangedPTS()

		if was_enabled and not self.timeshift_enabled:
			self.timeshift_enabled = False
			self.pts_LengthCheck_timer.stop()

	def restartTimeshift(self):
		self.activatePermanentTimeshift()
		Notifications.AddNotification(MessageBox, _("PTS-Plugin: Restarting Timeshift!"), MessageBox.TYPE_INFO, timeout=5)

	def saveTimeshiftPopup(self):
		self.session.openWithCallback(self.saveTimeshiftPopupCallback, ChoiceBox, \
			title=_("The Timeshift record was not saved yet!\nWhat do you want to do now with the timeshift file?"), \
			list=((_("Save Timeshift as Movie and stop recording"), "saveTimeshift"), \
			(_("Save Timeshift as Movie and continue recording"), "savetimeshiftandrecord"), \
			(_("Don't save Timeshift as Movie"), "noSave")))

	def saveTimeshiftPopupCallback(self, answer):
		if answer is None:
			return

		if answer[1] == "saveTimeshift":
			self.saveTimeshiftActions("saveTimeshift", self.save_timeshift_postaction)
		elif answer[1] == "savetimeshiftandrecord":
			self.saveTimeshiftActions("savetimeshiftandrecord", self.save_timeshift_postaction)
		elif answer[1] == "noSave":
			self.save_current_timeshift = False
			self.saveTimeshiftActions("noSave", self.save_timeshift_postaction)

	def saveTimeshiftEventPopup(self, view_only = False):
		filecount = 0
		entrylist = []
		if view_only:
			entrylist.append((_("Exit from view event"), "no"))
		entrylist.append((_("Current Event:")+" %s" % (self.pts_curevent_name), "saveTimeshift"))

		filelist = os_listdir(config.usage.timeshift_path.value)

		if filelist is not None:
			filelist.sort()

		for filename in filelist:
			if (filename.startswith("pts_livebuffer.") is True) and (filename.endswith(".del") is False and filename.endswith(".meta") is False and filename.endswith(".eit") is False and filename.endswith(".copy") is False):
				statinfo = os_stat("%s/%s" % (config.usage.timeshift_path.value,filename))
				if statinfo.st_mtime < (time()-5.0):
					# Get Event Info from meta file
					readmetafile = open("%s/%s.meta" % (config.usage.timeshift_path.value,filename), "r")
					servicerefname = readmetafile.readline()[0:-1]
					eventname = readmetafile.readline()[0:-1]
					description = readmetafile.readline()[0:-1]
					begintime = readmetafile.readline()[0:-1]
					readmetafile.close()

					# Add Event to list
					filecount += 1
					entrylist.append((_("Record") + " #%s (%s): %s" % (filecount,strftime("%H:%M",localtime(int(begintime))),eventname), "%s" % filename))
		self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, title=_("Which event do you want to save permanently?"), list=entrylist)

	def saveTimeshiftActions(self, action=None, postaction=None):
		self.save_timeshift_postaction = postaction

		if action is None:
			if config.plugins.pts.favoriteSaveAction.value == "askuser":
				self.saveTimeshiftPopup()
				return
			elif config.plugins.pts.favoriteSaveAction.value == "saveTimeshift":
				self.SaveTimeshift()
			elif config.plugins.pts.favoriteSaveAction.value == "savetimeshiftandrecord":
				if self.pts_curevent_end > time():
					self.SaveTimeshift(mergelater=True)
					self.ptsRecordCurrentEvent()
				else:
					self.SaveTimeshift()
			elif config.plugins.pts.favoriteSaveAction.value == "noSave":
				config.plugins.pts.isRecording.value = False
				self.save_current_timeshift = False
				self.zap_postaction = True
		elif action == "saveTimeshift":
			self.SaveTimeshift()
		elif action == "savetimeshiftandrecord":
			if self.pts_curevent_end > time():
				self.SaveTimeshift(mergelater=True)
				self.ptsRecordCurrentEvent()
			else:
				self.SaveTimeshift()
		elif action == "noSave":
			config.plugins.pts.isRecording.value = False
			self.save_current_timeshift = False
			self.zap_postaction = True

		# Get rid of old timeshift file before E2 truncates its filesize
		if self.save_timeshift_postaction is not None:
			self.eraseTimeshiftFile()

		# Post PTS Actions like ZAP or whatever the user requested
		if self.save_timeshift_postaction == "zapUp":
			self.zap_postaction = True
			InfoBarChannelSelection.zapUp(self)
		elif self.save_timeshift_postaction == "zapDown":
			self.zap_postaction = True
			InfoBarChannelSelection.zapDown(self)
		elif self.save_timeshift_postaction == "historyBack":
			InfoBarChannelSelection.historyBack(self)
		elif self.save_timeshift_postaction == "historyNext":
			InfoBarChannelSelection.historyNext(self)
		elif self.save_timeshift_postaction == "switchChannelUp":
			self.zap_postaction = True
			InfoBarChannelSelection.switchChannelUp(self)
		elif self.save_timeshift_postaction == "switchChannelDown":
			self.zap_postaction = True
			InfoBarChannelSelection.switchChannelDown(self)
		elif self.save_timeshift_postaction == "openServiceList":
			self.zap_postaction = True
			InfoBarChannelSelection.openServiceList(self)
		elif self.save_timeshift_postaction == "showRadioChannelList":
			self.zap_postaction = True
			InfoBarChannelSelection.showRadioChannelList(self, zap=True)
		elif self.save_timeshift_postaction == "standby":
			Notifications.AddNotification(Screens_Standby_Standby)

	def SaveTimeshift(self, timeshiftfile=None, mergelater=False):
		self.save_current_timeshift = False
		savefilename = None

		if timeshiftfile is not None:
			savefilename = timeshiftfile

		if savefilename is None:
			for filename in os_listdir(config.usage.timeshift_path.value):
				if filename.startswith("timeshift.") and not filename.endswith(".sc") and not filename.endswith(".del") and not filename.endswith(".copy"):
					try:
						statinfo = os_stat("%s/%s" % (config.usage.timeshift_path.value,filename))
						if statinfo.st_mtime > (time()-5.0):
							savefilename=filename
					except Exception, errormsg:
						Notifications.AddNotification(MessageBox, _("PTS Plugin Error: %s" % (errormsg)), MessageBox.TYPE_ERROR)

		if savefilename is None:
			Notifications.AddNotification(MessageBox, _("No Timeshift found to save as recording!"), MessageBox.TYPE_ERROR)
		else:
			timeshift_saved = True
			timeshift_saveerror1 = ""
			timeshift_saveerror2 = ""
			metamergestring = ""

			config.plugins.pts.isRecording.value = True

			if mergelater:
				self.pts_mergeRecords_timer.start(120000, True)
				metamergestring = "pts_merge\n"

			try:
				if timeshiftfile is None:
					# Save Current Event by creating hardlink to ts file
					if self.pts_starttime >= (time()-60):
						self.pts_starttime -= 60
					ptsfilename = "%s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station,self.pts_curevent_name)
					try:
						if config.usage.setup_level.index >= 2:
							if config.recording.filename_composition.value == "long" and self.pts_curevent_name != pts_curevent_description:
								ptsfilename = "%s - %s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station,self.pts_curevent_name,self.pts_curevent_description)
							elif config.recording.filename_composition.value == "short":
								ptsfilename = "%s - %s" % (strftime("%Y%m%d",localtime(self.pts_starttime)),self.pts_curevent_name)
					except Exception, errormsg:
						print "PTS-Plugin: Using default filename"

					if config.recording.ascii_filenames.value:
						ptsfilename = ASCIItranslit.legacyEncode(ptsfilename)

					fullname = Directories.getRecordingFilename(ptsfilename,config.usage.default_path.value)
					os_link("%s/%s" % (config.usage.timeshift_path.value,savefilename), "%s.ts" % (fullname))
					metafile = open("%s.ts.meta" % (fullname), "w")
					metafile.write("%s\n%s\n%s\n%i\n%s" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime),metamergestring))
					metafile.close()
					self.ptsCreateEITFile(fullname)
				elif timeshiftfile.startswith("pts_livebuffer"):
					# Save stored timeshift by creating hardlink to ts file
					readmetafile = open("%s/%s.meta" % (config.usage.timeshift_path.value,timeshiftfile), "r")
					servicerefname = readmetafile.readline()[0:-1]
					eventname = readmetafile.readline()[0:-1]
					description = readmetafile.readline()[0:-1]
					begintime = readmetafile.readline()[0:-1]
					readmetafile.close()

					ptsfilename = "%s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(int(begintime))),self.pts_curevent_station,eventname)
					try:
						if config.usage.setup_level.index >= 2:
							if config.recording.filename_composition.value == "long" and eventname != description:
								ptsfilename = "%s - %s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(int(begintime))),self.pts_curevent_station,eventname,description)
							elif config.recording.filename_composition.value == "short":
								ptsfilename = "%s - %s" % (strftime("%Y%m%d",localtime(int(begintime))),eventname)
					except Exception, errormsg:
						print "PTS-Plugin: Using default filename"

					if config.recording.ascii_filenames.value:
						ptsfilename = ASCIItranslit.legacyEncode(ptsfilename)

					fullname=Directories.getRecordingFilename(ptsfilename,config.usage.default_path.value)
					os_link("%s/%s" % (config.usage.timeshift_path.value,timeshiftfile),"%s.ts" % (fullname))
					os_link("%s/%s.meta" % (config.usage.timeshift_path.value,timeshiftfile),"%s.ts.meta" % (fullname))
					if fileExists("%s/%s.eit" % (config.usage.timeshift_path.value,timeshiftfile)):
						os_link("%s/%s.eit" % (config.usage.timeshift_path.value,timeshiftfile),"%s.eit" % (fullname))

					# Add merge-tag to metafile
					if mergelater:
						metafile = open("%s.ts.meta" % (fullname), "a")
						metafile.write("%s\n" % (metamergestring))
						metafile.close()

				# Create AP and SC Files when not merging
				if not mergelater:
					self.ptsCreateAPSCFiles(fullname+".ts")

			except Exception, errormsg:
				timeshift_saved = False
				timeshift_saveerror1 = errormsg

			# Hmpppf! Saving Timeshift via Hardlink-Method failed. Probably other device?
			# Let's try to copy the file in background now! This might take a while ...
			if not timeshift_saved:
				try:
					stat = statvfs(config.usage.default_path.value)
					freespace = stat.f_bfree / 1000 * stat.f_bsize / 1000
					randomint = randint(1, 999)

					if timeshiftfile is None:
						# Get Filesize for Free Space Check
						filesize = int(os_path.getsize("%s/%s" % (config.usage.timeshift_path.value,savefilename)) / (1024*1024))

						# Save Current Event by copying it to the other device
						if filesize <= freespace:
							os_link("%s/%s" % (config.usage.timeshift_path.value,savefilename), "%s/%s.%s.copy" % (config.usage.timeshift_path.value,savefilename,randomint))
							copy_file = savefilename
							metafile = open("%s.ts.meta" % (fullname), "w")
							metafile.write("%s\n%s\n%s\n%i\n%s" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime),metamergestring))
							metafile.close()
							self.ptsCreateEITFile(fullname)
					elif timeshiftfile.startswith("pts_livebuffer"):
						# Get Filesize for Free Space Check
						filesize = int(os_path.getsize("%s/%s" % (config.usage.timeshift_path.value, timeshiftfile)) / (1024*1024))

						# Save stored timeshift by copying it to the other device
						if filesize <= freespace:
							os_link("%s/%s" % (config.usage.timeshift_path.value,timeshiftfile), "%s/%s.%s.copy" % (config.usage.timeshift_path.value,timeshiftfile,randomint))
							copyfile("%s/%s.meta" % (config.usage.timeshift_path.value,timeshiftfile),"%s.ts.meta" % (fullname))
							if fileExists("%s/%s.eit" % (config.usage.timeshift_path.value,timeshiftfile)):
								copyfile("%s/%s.eit" % (config.usage.timeshift_path.value,timeshiftfile),"%s.eit" % (fullname))
							copy_file = timeshiftfile

						# Add merge-tag to metafile
						if mergelater:
							metafile = open("%s.ts.meta" % (fullname), "a")
							metafile.write("%s\n" % (metamergestring))
							metafile.close()

					# Only copy file when enough disk-space available!
					if filesize <= freespace:
						timeshift_saved = True
						copy_file = copy_file+"."+str(randomint)

						# Get Event Info from meta file
						if fileExists("%s.ts.meta" % (fullname)):
							readmetafile = open("%s.ts.meta" % (fullname), "r")
							servicerefname = readmetafile.readline()[0:-1]
							eventname = readmetafile.readline()[0:-1]
						else:
							eventname = "";

						JobManager.AddJob(CopyTimeshiftJob(self, "cp \"%s/%s.copy\" \"%s.ts\"" % (config.usage.timeshift_path.value,copy_file,fullname), copy_file, fullname, eventname))
						if not Screens.Standby.inTryQuitMainloop and not Screens.Standby.inStandby and not mergelater and self.save_timeshift_postaction != "standby":
							Notifications.AddNotification(MessageBox, _("Saving timeshift as movie now. This might take a while!"), MessageBox.TYPE_INFO, timeout=5)
					else:
						timeshift_saved = False
						timeshift_saveerror1 = ""
						timeshift_saveerror2 = _("Not enough free Diskspace!\n\nFilesize: %sMB\nFree Space: %sMB\nPath: %s") % (filesize,freespace,config.usage.default_path.value)

				except Exception, errormsg:
					timeshift_saved = False
					timeshift_saveerror2 = errormsg

			if not timeshift_saved:
				config.plugins.pts.isRecording.value = False
				self.save_timeshift_postaction = None
				errormessage = str(timeshift_saveerror1) + "\n" + str(timeshift_saveerror2)
				Notifications.AddNotification(MessageBox, _("Timeshift save failed!")+"\n\n%s" % errormessage, MessageBox.TYPE_ERROR)


	def ptsCleanTimeshiftFolder(self):
		if not config.plugins.pts.enabled.value or self.ptsCheckTimeshiftPath() is False or self.session.screen["Standby"].boolean is True:
			return

		try:
			for filename in os_listdir(config.usage.timeshift_path.value):
				if (filename.startswith("timeshift.") or filename.startswith("pts_livebuffer.")) and not filename.endswith(".sc") and (filename.endswith(".del") is False and filename.endswith(".copy") is False and filename.endswith(".meta") is False and filename.endswith(".eit") is False):

					statinfo = os_stat("%s/%s" % (config.usage.timeshift_path.value,filename))
					# if no write for 5 sec = stranded timeshift
					if statinfo.st_mtime < (time()-5.0):
						print "PTS-Plugin: Erasing stranded timeshift %s" % filename
						self.eraseFile("%s/%s" % (config.usage.timeshift_path.value,filename))

						# Delete Meta and EIT File too
						if filename.startswith("pts_livebuffer.") is True:
							self.BgFileEraser.erase("%s/%s.meta" % (config.usage.timeshift_path.value,filename))
							self.BgFileEraser.erase("%s/%s.eit" % (config.usage.timeshift_path.value,filename))
		except:
			print "PTS: IO-Error while cleaning Timeshift Folder ..."

	def ptsGetEventInfo(self):
		event = None
		try:
			serviceref = self.session.nav.getCurrentlyPlayingServiceReference()
			serviceHandler = eServiceCenter.getInstance()
			info = serviceHandler.info(serviceref)

			self.pts_curevent_servicerefname = serviceref.toString()
			self.pts_curevent_station = info.getName(serviceref)

			service = self.session.nav.getCurrentService()
			info = service and service.info()
			event = info and info.getEvent(0)
		except Exception, errormsg:
			Notifications.AddNotification(MessageBox, _("Getting Event Info failed!")+"\n\n%s" % errormsg, MessageBox.TYPE_ERROR, timeout=10)

		if event is not None:
			curEvent = parseEvent(event)
			self.pts_curevent_begin = int(curEvent[0])
			self.pts_curevent_end = int(curEvent[1])
			self.pts_curevent_name = curEvent[2]
			self.pts_curevent_description = curEvent[3]
			self.pts_curevent_eventid = curEvent[4]
		else: 
			self.pts_curevent_name = _("%s (timeshift)") % self.pts_curevent_station
			begin_date = strftime("%H:%M %d.%m.%Y", localtime(time()))
			self.pts_curevent_description = _("instant record") + " - " + begin_date
			begin = int(time())
			self.pts_curevent_begin = begin
			self.pts_curevent_end = begin + int(config.plugins.pts.length_no_epg.value*60)


	def ptsFrontpanelActions(self, action=None):
		if self.session.nav.RecordTimer.isRecording() or SystemInfo.get("NumFrontpanelLEDs", 0) == 0:
			return

		try:
			if action == "start":
				if fileExists("/proc/stb/fp/led_set_pattern"):
					open("/proc/stb/fp/led_set_pattern", "w").write("0xa7fccf7a")
				elif fileExists("/proc/stb/fp/led0_pattern"):
					open("/proc/stb/fp/led0_pattern", "w").write("0x55555555")
				if fileExists("/proc/stb/fp/led_pattern_speed"):
					open("/proc/stb/fp/led_pattern_speed", "w").write("20")
				elif fileExists("/proc/stb/fp/led_set_speed"):
					open("/proc/stb/fp/led_set_speed", "w").write("20")
			elif action == "stop":
				if fileExists("/proc/stb/fp/led_set_pattern"):
					open("/proc/stb/fp/led_set_pattern", "w").write("0")
				elif fileExists("/proc/stb/fp/led0_pattern"):
					open("/proc/stb/fp/led0_pattern", "w").write("0")
		except Exception, errormsg:
			print "PTS Plugin: %s" % (errormsg)

	def ptsCreateHardlink(self):
		for filename in os_listdir(config.usage.timeshift_path.value):
			if filename.startswith("timeshift.") and not filename.endswith(".sc") and not filename.endswith(".del") and not filename.endswith(".copy"):
				try:
					statinfo = os_stat("%s/%s" % (config.usage.timeshift_path.value,filename))
					if statinfo.st_mtime > (time()-5.0):
						try:
							self.eraseFile("%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount))
							self.BgFileEraser.erase("%s/pts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_eventcount))
						except Exception, errormsg:
							print "PTS Plugin: %s" % (errormsg)

						try:
							# Create link to pts_livebuffer file
							os_link("%s/%s" % (config.usage.timeshift_path.value,filename), "%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount))

							# Create a Meta File
							metafile = open("%s/pts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_eventcount), "w")
							metafile.write("%s\n%s\n%s\n%i\n" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime)))
							metafile.close()
						except Exception, errormsg:
							Notifications.AddNotification(MessageBox, _("Creating Hardlink to Timeshift file failed!")+"\n"+_("The Filesystem on your Timeshift-Device does not support hardlinks.\nMake sure it is formated in EXT2 or EXT3!")+"\n\n%s" % errormsg, MessageBox.TYPE_ERROR)

						# Create EIT File
						self.ptsCreateEITFile("%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount))

						# Permanent Recording Hack
						if config.plugins.pts.permanentrecording.value:
							try:
								fullname = Directories.getRecordingFilename("%s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station,self.pts_curevent_name),config.usage.default_path.value)
								os_link("%s/%s" % (config.usage.timeshift_path.value,filename), "%s.ts" % (fullname))
								# Create a Meta File
								metafile = open("%s.ts.meta" % (fullname), "w")
								metafile.write("%s\n%s\n%s\n%i\nautosaved\n" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime)))
								metafile.close()
							except Exception, errormsg:
								print "PTS Plugin: %s" % (errormsg)
				except Exception, errormsg:
					errormsg = str(errormsg)
					if errormsg.find('Input/output error') != -1:
						errormsg += _("\nAn Input/output error usually indicates a corrupted filesystem! Please check the filesystem of your timeshift-device!")
					Notifications.AddNotification(MessageBox, _("Creating Hardlink to Timeshift file failed!")+"\n%s" % (errormsg), MessageBox.TYPE_ERROR)

	def ptsRecordCurrentEvent(self):
			recording = RecordTimerEntry(ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference()), time(), self.pts_curevent_end, self.pts_curevent_name, self.pts_curevent_description, self.pts_curevent_eventid, dirname = config.usage.default_path.value)
			recording.dontSave = True
			self.session.nav.RecordTimer.record(recording)
			self.recording.append(recording)

	def ptsMergeRecords(self):
		if self.session.nav.RecordTimer.isRecording():
			self.pts_mergeRecords_timer.start(120000, True)
			return

		ptsmergeSRC = ""
		ptsmergeDEST = ""
		ptsmergeeventname = ""
		ptsgetnextfile = False
		ptsfilemerged = False

		filelist = os_listdir(config.usage.default_path.value)

		if filelist is not None:
			filelist.sort()

		for filename in filelist:
			if filename.endswith(".meta"):
				# Get Event Info from meta file
				readmetafile = open("%s/%s" % (config.usage.default_path.value,filename), "r")
				servicerefname = readmetafile.readline()[0:-1]
				eventname = readmetafile.readline()[0:-1]
				eventtitle = readmetafile.readline()[0:-1]
				eventtime = readmetafile.readline()[0:-1]
				eventtag = readmetafile.readline()[0:-1]
				readmetafile.close()

				if ptsgetnextfile:
					ptsgetnextfile = False
					ptsmergeSRC = filename[0:-5]

					if ASCIItranslit.legacyEncode(eventname) == ASCIItranslit.legacyEncode(ptsmergeeventname):
						# Copy EIT File
						if fileExists("%s/%s.eit" % (config.usage.default_path.value, ptsmergeSRC[0:-3])):
							copyfile("%s/%s.eit" % (config.usage.default_path.value, ptsmergeSRC[0:-3]),"%s/%s.eit" % (config.usage.default_path.value, ptsmergeDEST[0:-3]))

						# Delete AP and SC Files
						self.BgFileEraser.erase("%s/%s.ap" % (config.usage.default_path.value, ptsmergeDEST))
						self.BgFileEraser.erase("%s/%s.sc" % (config.usage.default_path.value, ptsmergeDEST))

						# Add Merge Job to JobManager
						JobManager.AddJob(MergeTimeshiftJob(self, "cat \"%s/%s\" >> \"%s/%s\"" % (config.usage.default_path.value,ptsmergeSRC,config.usage.default_path.value,ptsmergeDEST), ptsmergeSRC, ptsmergeDEST, eventname))
						config.plugins.pts.isRecording.value = True
						ptsfilemerged = True
					else:
						ptsgetnextfile = True

				if eventtag == "pts_merge" and not ptsgetnextfile:
					ptsgetnextfile = True
					ptsmergeDEST = filename[0:-5]
					ptsmergeeventname = eventname
					ptsfilemerged = False

					# If still recording or transfering, try again later ...
					if fileExists("%s/%s" % (config.usage.default_path.value,ptsmergeDEST)):
						statinfo = os_stat("%s/%s" % (config.usage.default_path.value,ptsmergeDEST))
						if statinfo.st_mtime > (time()-10.0):
							self.pts_mergeRecords_timer.start(120000, True)
							return

					# Rewrite Meta File to get rid of pts_merge tag
					metafile = open("%s/%s.meta" % (config.usage.default_path.value,ptsmergeDEST), "w")
					metafile.write("%s\n%s\n%s\n%i\n" % (servicerefname,eventname.replace("\n", ""),eventtitle.replace("\n", ""),int(eventtime)))
					metafile.close()

		# Merging failed :(
		if not ptsfilemerged and ptsgetnextfile:
			Notifications.AddNotification(MessageBox,_("PTS-Plugin: Merging records failed!"), MessageBox.TYPE_ERROR)

	def ptsCreateAPSCFiles(self, filename):
		if fileExists(filename, 'r'):
			if fileExists(filename+".meta", 'r'):
				# Get Event Info from meta file
				readmetafile = open(filename+".meta", "r")
				servicerefname = readmetafile.readline()[0:-1]
				eventname = readmetafile.readline()[0:-1]
			else:
				eventname = ""
			JobManager.AddJob(CreateAPSCFilesJob(self, "/usr/lib/enigma2/python/Plugins/Extensions/PermanentTimeshift/createapscfiles \"%s\"" % (filename), eventname))
		else:
			self.ptsSaveTimeshiftFinished()

	def ptsCreateEITFile(self, filename):
		if self.pts_curevent_eventid is not None:
			try:
				import eitsave
				serviceref = ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference()).ref.toString()
				eitsave.SaveEIT(serviceref, filename+".eit", self.pts_curevent_eventid, -1, -1)
			except Exception, errormsg:
				print "PTS Plugin: %s" % (errormsg)

	def ptsCopyFilefinished(self, srcfile, destfile):
		# Erase Source File
		if fileExists(srcfile):
			self.eraseFile(srcfile)

		# Restart Merge Timer
		if self.pts_mergeRecords_timer.isActive():
			self.pts_mergeRecords_timer.stop()
			self.pts_mergeRecords_timer.start(15000, True)
		else:
			# Create AP and SC Files
			self.ptsCreateAPSCFiles(destfile)

	def ptsMergeFilefinished(self, srcfile, destfile):
		if self.session.nav.RecordTimer.isRecording() or len(JobManager.getPendingJobs()) >= 1:
			# Rename files and delete them later ...
			self.pts_mergeCleanUp_timer.start(120000, True)
			os_system("echo \"\" > \"%s.pts.del\"" % (srcfile[0:-3]))
		else:
			# Delete Instant Record permanently now ... R.I.P.
			self.eraseFile("%s" % (srcfile))
			self.BgFileEraser.erase("%s.ap" % (srcfile))
			self.BgFileEraser.erase("%s.sc" % (srcfile))
			self.BgFileEraser.erase("%s.meta" % (srcfile))
			self.BgFileEraser.erase("%s.cuts" % (srcfile))
			self.BgFileEraser.erase("%s.eit" % (srcfile[0:-3]))

		# Create AP and SC Files
		self.ptsCreateAPSCFiles(destfile)

		# Run Merge-Process one more time to check if there are more records to merge
		self.pts_mergeRecords_timer.start(10000, True)

	def ptsSaveTimeshiftFinished(self):
		if not self.pts_mergeCleanUp_timer.isActive():
			self.ptsFrontpanelActions("stop")
			config.plugins.pts.isRecording.value = False

		if Screens.Standby.inTryQuitMainloop:
			self.pts_QuitMainloop_timer.start(30000, True)
		else:
			Notifications.AddNotification(MessageBox, _("Timeshift saved to your harddisk!"), MessageBox.TYPE_INFO, timeout = 5)

	def ptsMergePostCleanUp(self):
		if self.session.nav.RecordTimer.isRecording() or len(JobManager.getPendingJobs()) >= 1:
			config.plugins.pts.isRecording.value = True
			self.pts_mergeCleanUp_timer.start(120000, True)
			return

		self.ptsFrontpanelActions("stop")
		config.plugins.pts.isRecording.value = False

		filelist = os_listdir(config.usage.default_path.value)
		for filename in filelist:
			if filename.endswith(".pts.del"):
				srcfile = config.usage.default_path.value + "/" + filename[0:-8] + ".ts"
				self.eraseFile("%s" % (srcfile))
				self.BgFileEraser.erase("%s.ap" % (srcfile))
				self.BgFileEraser.erase("%s.sc" % (srcfile))
				self.BgFileEraser.erase("%s.meta" % (srcfile))
				self.BgFileEraser.erase("%s.cuts" % (srcfile))
				self.BgFileEraser.erase("%s.eit" % (srcfile[0:-3]))
				self.BgFileEraser.erase("%s.pts.del" % (srcfile[0:-3]))

				# Restart QuitMainloop Timer to give BgFileEraser enough time
				if Screens.Standby.inTryQuitMainloop and self.pts_QuitMainloop_timer.isActive():
					self.pts_QuitMainloop_timer.start(60000, True)

	def ptsTryQuitMainloop(self):
		if Screens.Standby.inTryQuitMainloop and (len(JobManager.getPendingJobs()) >= 1 or self.pts_mergeCleanUp_timer.isActive()):
			self.pts_QuitMainloop_timer.start(60000, True)
			return

		if Screens.Standby.inTryQuitMainloop and self.session.ptsmainloopvalue:
			self.session.dialog_stack = []
			self.session.summary_stack = [None]
			self.session.open(TryQuitMainloop, self.session.ptsmainloopvalue)

	def ptsGetSeekInfo(self):
		s = self.session.nav.getCurrentService()
		return s and s.seek()

	def ptsGetPosition(self):
		seek = self.ptsGetSeekInfo()
		if seek is None:
			return None
		pos = seek.getPlayPosition()
		if pos[0]:
			return 0
		return pos[1]

	def ptsGetLength(self):
		seek = self.ptsGetSeekInfo()
		if seek is None:
			return None
		length = seek.getLength()
		if length[0]:
			return 0
		return length[1]

	def ptsGetSaveTimeshiftStatus(self):
		return self.save_current_timeshift


	def ptsSeekPointerOK(self):
		if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			if not self.pvrstate_hide_timer.isActive():
				if self.seekstate != self.SEEK_STATE_PLAY:
					self.setSeekState(self.SEEK_STATE_PLAY)
				self.doShow()
				return

			length = self.ptsGetLength()
			position = self.ptsGetPosition()

			if length is None or position is None:
				return

			cur_pos = self.pvrStateDialog["PTSSeekPointer"].position
			jumptox = int(cur_pos[0]) - int(self.pts_seekpointer_MinX)
			jumptoperc = round((jumptox / 400.0) * 100, 0)
			jumptotime = int((length / 100) * jumptoperc)
			jumptodiff = position - jumptotime

			self.doSeekRelative(-jumptodiff)
		else:
			return

	def ptsSeekPointerLeft(self):
		if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			self.ptsMoveSeekPointer(direction="left")
		else:
			return

	def ptsSeekPointerRight(self):
		if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			self.ptsMoveSeekPointer(direction="right")
		else:
			return

	def ptsSeekPointerReset(self):
		if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MinX,self.pvrStateDialog["PTSSeekPointer"].position[1])

	def ptsSeekPointerSetCurrentPos(self):
		if not self.pts_pvrStateDialog == "PTSTimeshiftState" or not self.timeshift_enabled or not self.isSeekable():
			return

		position = self.ptsGetPosition()
		length = self.ptsGetLength()

		if length >= 1:
			tpixels = int((float(int((position*100)/length))/100)*400)
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MinX+tpixels, self.pvrStateDialog["PTSSeekPointer"].position[1])

	def ptsMoveSeekPointer(self, direction=None):
		if direction is None or self.pts_pvrStateDialog != "PTSTimeshiftState":
			return

		isvalidjump = False
		cur_pos = self.pvrStateDialog["PTSSeekPointer"].position
		InfoBarTimeshiftState._mayShow(self)

		if direction == "left":
			minmaxval = self.pts_seekpointer_MinX
			movepixels = -15
			if cur_pos[0]+movepixels > minmaxval:
				isvalidjump = True
		elif direction == "right":
			minmaxval = self.pts_seekpointer_MaxX
			movepixels = 15
			if cur_pos[0]+movepixels < minmaxval:
				isvalidjump = True
		else:
			return 0

		if isvalidjump:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(cur_pos[0]+movepixels,cur_pos[1])
		else:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(minmaxval,cur_pos[1])

	def ptsTimeshiftFileChanged(self):
		# Reset Seek Pointer
		if config.plugins.pts.enabled.value and config.plugins.pts.showinfobar.value:
			self.ptsSeekPointerReset()

		if self.pts_switchtolive:
			self.pts_switchtolive = False
			return

		if self.pts_seektoprevfile:
			if self.pts_currplaying == 1:
				self.pts_currplaying = config.plugins.pts.maxevents.value
			else:
				self.pts_currplaying -= 1
		else:
			if self.pts_currplaying == config.plugins.pts.maxevents.value:
				self.pts_currplaying = 1
			else:
				self.pts_currplaying += 1

		if not fileExists("%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_currplaying), 'r'):
			self.pts_currplaying = self.pts_eventcount

		# Set Eventname in PTS InfoBar
		if config.plugins.pts.enabled.value and config.plugins.pts.showinfobar.value and self.pts_pvrStateDialog == "PTSTimeshiftState":
			try:
				if self.pts_eventcount != self.pts_currplaying:
					readmetafile = open("%s/pts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_currplaying), "r")
					servicerefname = readmetafile.readline()[0:-1]
					eventname = readmetafile.readline()[0:-1]
					readmetafile.close()
					self.pvrStateDialog["eventname"].setText(eventname)
				else:
					self.pvrStateDialog["eventname"].setText("")
			except Exception, errormsg:
				self.pvrStateDialog["eventname"].setText("")

		# Get next pts file ...
		if self.pts_currplaying+1 > config.plugins.pts.maxevents.value:
			nextptsfile = 1
		else:
			nextptsfile = self.pts_currplaying+1

		# Seek to previous file
		if self.pts_seektoprevfile:
			self.pts_seektoprevfile = False

			if fileExists("%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value,nextptsfile), 'r'):
				self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (nextptsfile))

			self.ptsSeekBackHack()
		else:
			if fileExists("%s/pts_livebuffer.%s" % (config.usage.timeshift_path.value,nextptsfile), 'r') and nextptsfile <= self.pts_eventcount:
				self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (nextptsfile))
			if nextptsfile == self.pts_currplaying:
				self.pts_switchtolive = True
				self.ptsSetNextPlaybackFile("")

	def ptsSetNextPlaybackFile(self, nexttsfile):
		ts = self.getTimeshift()
		if ts is None:
			return

		try:
			ts.setNextPlaybackFile("%s/%s" % (config.usage.timeshift_path.value,nexttsfile))
		except:
			print "PTS-Plugin: setNextPlaybackFile() not supported by OE. Enigma2 too old !?"

	def ptsSeekBackHack(self):
		if not config.plugins.pts.enabled.value or not self.timeshift_enabled:
			return

		self.setSeekState(self.SEEK_STATE_PAUSE)
		self.doSeek(-90000*4) # seek ~4s before end
		self.pts_SeekBack_timer.start(1000, True)

	def ptsSeekBackTimer(self):
		if self.pts_lastseekspeed == 0:
			self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
		else:
			self.setSeekState(self.makeStateBackward(int(-self.pts_lastseekspeed)))

	def ptsCheckTimeshiftPath(self):
		if self.pts_pathchecked:
			return True
		else:
			if fileExists(config.usage.timeshift_path.value, 'w'):
				self.pts_pathchecked = True
				return True
			else:
				Notifications.AddNotification(MessageBox, _("Could not activate Permanent-Timeshift!\nTimeshift-Path does not exist"), MessageBox.TYPE_ERROR, timeout=15)
				if self.pts_delay_timer.isActive():
					self.pts_delay_timer.stop()
				if self.pts_cleanUp_timer.isActive():
					self.pts_cleanUp_timer.stop()
				return False

	def ptsTimerEntryStateChange(self, timer):
		if config.plugins.pts.mode.value == "1":
			return
		if not config.plugins.pts.enabled.value or not config.plugins.pts.stopwhilerecording.value:
			return

		self.pts_record_running = self.session.nav.RecordTimer.isRecording()

		# Abort here when box is in standby mode
		if self.session.screen["Standby"].boolean is True:
			return

		# Stop Timeshift when Record started ...
		if timer.state == TimerEntry.StateRunning and self.timeshift_enabled and self.pts_record_running:
			if self.ptsLiveTVStatus() is False:
				self.timeshift_enabled =False
				self.pts_LengthCheck_timer.stop()
				return

			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)

			if self.isSeekable():
				Notifications.AddNotification(MessageBox,_("Record started! Stopping timeshift now ..."), MessageBox.TYPE_INFO, timeout=5)
			self.stopTimeshiftConfirmed(True, False)
			if config.plugins.pts.show_icon.value:
				if self.TimeshiftIndicator is not None:
					self.TimeshiftIndicator.hide()
				self.TimeshiftIndicator = None

		# Restart Timeshift when all records stopped
		if timer.state == TimerEntry.StateEnded and not self.timeshift_enabled and not self.pts_record_running:
			self.activatePermanentTimeshift()


		# Restart Merge-Timer when all records stopped
		if timer.state == TimerEntry.StateEnded and self.pts_mergeRecords_timer.isActive():
			self.pts_mergeRecords_timer.stop()
			self.pts_mergeRecords_timer.start(15000, True)

		# Restart FrontPanel LED when still copying or merging files
		# ToDo: Only do this on PTS Events and not events from other jobs
		if timer.state == TimerEntry.StateEnded and (len(JobManager.getPendingJobs()) >= 1 or self.pts_mergeRecords_timer.isActive()):
			self.ptsFrontpanelActions("start")
			config.plugins.pts.isRecording.value = True

	def ptsLiveTVStatusORG(self):
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		sTSID = info and info.getInfo(iServiceInformation.sTSID) or -1

		if sTSID is None or sTSID == -1:
			return False
		else:
			return True

	def ptsLiveTVStatus(self):
		service = self.session.nav.getCurrentService()
		ts = service and service.timeshift()
		if ts is None:
			return False
		else:
			return True

	def ptsLengthCheck(self):
		# Check if we are in TV Mode ...
		if self.ptsLiveTVStatus() is False:
			self.timeshift_enabled = False
			self.pts_LengthCheck_timer.stop()
			return

		if config.plugins.pts.stopwhilerecording.value and self.pts_record_running:
			return

		# Length Check
		if config.plugins.pts.enabled.value and self.session.screen["Standby"].boolean is not True and self.timeshift_enabled and (time() - self.pts_starttime) >= (config.plugins.pts.maxlength.value * 60):
			if self.save_current_timeshift:
				self.saveTimeshiftActions("saveTimeshift")
				self.activatePermanentTimeshift()
				self.save_current_timeshift = True
			else:
				self.activatePermanentTimeshift()
			Notifications.AddNotification(MessageBox,_("Maximum Timeshift length per Event reached!\nRestarting Timeshift now ..."), MessageBox.TYPE_INFO, timeout=5)

	def SaveCurrentTimeshiftPTS(self):
		self.session.openWithCallback(self.CallbackSaveCurrentTimeshiftPTS, MessageBox, _("Reminder, you have previously chosen to save timeshift file at end of event!\nThis action will be canceled.\nSave the current event now?"), MessageBox.TYPE_YESNO)

	def CallbackSaveCurrentTimeshiftPTS(self, answer):
		if answer:
			self.SaveTimeshift(timeshiftfile="pts_livebuffer.%s" % self.pts_eventcount)
			ts = self.getTimeshift()
			if ts:
				try:
					ts.stopTimeshift()
					ts.startTimeshift()
					self.ptsCreateHardlink()
				except:
					print "PTS-Plugin: Error restart timeshift!"

#Replace the InfoBar with our version ;)
Screens.InfoBar.InfoBar = InfoBar

################################
##### Class Standby Hack 1 #####
################################
TryQuitMainloop_getRecordEvent = Screens.Standby.TryQuitMainloop.getRecordEvent

class TryQuitMainloopPTS(TryQuitMainloop):
	def __init__(self, session, retvalue=1, timeout=-1, default_yes = True):
		TryQuitMainloop.__init__(self, session, retvalue, timeout, default_yes)

		self.session.ptsmainloopvalue = retvalue

	def getRecordEvent(self, recservice, event):
		if event == iRecordableService.evEnd and (config.plugins.pts.isRecording.value or len(JobManager.getPendingJobs()) >= 1):
			return
		else:
			TryQuitMainloop_getRecordEvent(self, recservice, event)

Screens.Standby.TryQuitMainloop = TryQuitMainloopPTS

################################
##### Class Standby Hack 2 #####
################################

Screens_Standby_Standby = Screens.Standby.Standby

class StandbyPTS(Standby):
	def __init__(self, session, StandbyCounterIncrease=True):
		if InfoBar and InfoBar.instance and InfoBar.ptsGetSaveTimeshiftStatus(InfoBar.instance):
			self.skin = """<screen position="0,0" size="0,0"/>"""
			Screen.__init__(self, session)
			self.onFirstExecBegin.append(self.showMessageBox)
			self.onHide.append(self.close)
		else:
			Standby.__init__(self, session, StandbyCounterIncrease)
			self.skinName = "Standby"

	def showMessageBox(self):
		if InfoBar and InfoBar.instance:
			InfoBar.saveTimeshiftActions(InfoBar.instance, postaction="standby")

Screens.Standby.Standby = StandbyPTS

############
#zapUp Hack#
############
InfoBarChannelSelection_zapUp = InfoBarChannelSelection.zapUp

def zapUp(self):
	if self.pts_blockZap_timer.isActive():
		return

	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="zapUp")
	else:
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.isSeekable() and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		self.zap_postaction = False
		InfoBarChannelSelection_zapUp(self)

InfoBarChannelSelection.zapUp = zapUp

##############
#zapDown Hack#
##############
InfoBarChannelSelection_zapDown = InfoBarChannelSelection.zapDown

def zapDown(self):
	if self.pts_blockZap_timer.isActive():
		return

	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="zapDown")
	else:
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.isSeekable() and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		self.zap_postaction = False
		InfoBarChannelSelection_zapDown(self)

InfoBarChannelSelection.zapDown = zapDown

##################
#historyBack Hack#
##################
InfoBarChannelSelection_historyBack = InfoBarChannelSelection.historyBack

def historyBack(self):
	if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
		InfoBarTimeshiftState._mayShow(self)
		self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MinX, self.pvrStateDialog["PTSSeekPointer"].position[1])
		if self.seekstate != self.SEEK_STATE_PLAY:
			self.setSeekState(self.SEEK_STATE_PLAY)
		self.ptsSeekPointerOK()
	elif self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="historyBack")
	else:
		InfoBarChannelSelection_historyBack(self)

InfoBarChannelSelection.historyBack = historyBack

##################
#historyNext Hack#
##################
InfoBarChannelSelection_historyNext = InfoBarChannelSelection.historyNext

def historyNext(self):
	if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
		InfoBarTimeshiftState._mayShow(self)
		self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MaxX, self.pvrStateDialog["PTSSeekPointer"].position[1])
		if self.seekstate != self.SEEK_STATE_PLAY:
			self.setSeekState(self.SEEK_STATE_PLAY)
		self.ptsSeekPointerOK()
	elif self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="historyNext")
	else:
		InfoBarChannelSelection_historyNext(self)

InfoBarChannelSelection.historyNext = historyNext

######################
#switchChannelUp Hack#
######################
InfoBarChannelSelection_switchChannelUp = InfoBarChannelSelection.switchChannelUp

def switchChannelUp(self):
	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="switchChannelUp")
	else:
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.isSeekable() and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		self.zap_postaction = False
		InfoBarChannelSelection_switchChannelUp(self)

InfoBarChannelSelection.switchChannelUp = switchChannelUp

########################
#switchChannelDown Hack#
########################
InfoBarChannelSelection_switchChannelDown = InfoBarChannelSelection.switchChannelDown

def switchChannelDown(self):
	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="switchChannelDown")
	else:
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.isSeekable() and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		self.zap_postaction = False
		InfoBarChannelSelection_switchChannelDown(self)

InfoBarChannelSelection.switchChannelDown = switchChannelDown

######################
#openServiceList Hack#
######################
InfoBarChannelSelection_openServiceList = InfoBarChannelSelection.openServiceList

def openServiceList(self):
	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="openServiceList")
	else:
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.isSeekable() and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		self.zap_postaction = False
		InfoBarChannelSelection_openServiceList(self)

InfoBarChannelSelection.openServiceList = openServiceList

###########################
#showRadioChannelList Hack#
###########################
InfoBarChannelSelection_showRadioChannelList = InfoBarChannelSelection.showRadioChannelList

def showRadioChannelList(self, zap=False):
	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self, postaction="showRadioChannelList")
	else:
		if config.plugins.pts.enabled.value and self.timeshift_enabled and config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.isSeekable() and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		self.zap_postaction = False
		InfoBarChannelSelection_showRadioChannelList(self, zap)

InfoBarChannelSelection.showRadioChannelList = showRadioChannelList

#######################
#InfoBarNumberZap Hack#
#######################
InfoBarNumberZap_keyNumberGlobal = InfoBarNumberZap.keyNumberGlobal

def keyNumberGlobal(self, number):
	if self.pts_pvrStateDialog == "PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable() and number == 0:
		InfoBarTimeshiftState._mayShow(self)
		self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MaxX/2, self.pvrStateDialog["PTSSeekPointer"].position[1])
		if self.seekstate != self.SEEK_STATE_PLAY:
			self.setSeekState(self.SEEK_STATE_PLAY)
		self.ptsSeekPointerOK()
		return

	if self.pts_blockZap_timer.isActive():
		return
		
	if self.save_current_timeshift and self.timeshift_enabled:
		InfoBar.saveTimeshiftActions(self)
		if config.plugins.pts.check_timeshift.value:
			self.zap_postaction = True
		return
	if config.plugins.pts.enabled.value and self.timeshift_enabled:
		if config.plugins.pts.check_timeshift.value:
			if config.plugins.pts.mode.value == "1":
				if not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
			else:
				if self.seek_action and not self.zap_postaction:
					try:
						config.usage.check_timeshift.setValue(True)
					except:
						pass
				else:
					try:
						config.usage.check_timeshift.setValue(False)
					except:
						pass
		else:
			try:
				config.usage.check_timeshift.setValue(False)
			except:
				pass
	self.zap_postaction = False
	InfoBarNumberZap_keyNumberGlobal(self, number)


InfoBarNumberZap.keyNumberGlobal = keyNumberGlobal

#############################
# getNextRecordingTime Hack #
#############################
RecordTimer_getNextRecordingTime = RecordTimer.getNextRecordingTime

def getNextRecordingTime(self):
	nextrectime = RecordTimer_getNextRecordingTime(self)
	faketime = time()+300

	if config.plugins.pts.isRecording.value or len(JobManager.getPendingJobs()) >= 1:
		if nextrectime > 0 and nextrectime < faketime:
			return nextrectime
		else:
			return faketime
	else:
		return nextrectime

RecordTimer.getNextRecordingTime = getNextRecordingTime

############################
#InfoBarTimeshiftState Hack#
############################
def _mayShow(self):
	ts = self.getTimeshift()
	timeshiftEnabled = ts and ts.isTimeshiftEnabled()
	if InfoBar and InfoBar.instance and self.execing and timeshiftEnabled and self.isSeekable():
		InfoBar.ptsSeekPointerSetCurrentPos(self)
		self.pvrStateDialog.show()

		self.pvrstate_hide_timer = eTimer()
		self.pvrstate_hide_timer.callback.append(self.pvrStateDialog.hide)
		self.pvrstate_hide_timer.stop()
		
		if self.seekstate == self.SEEK_STATE_PLAY:
			idx = config.usage.infobar_timeout.index
			if not idx:
				idx = 5
			self.pvrstate_hide_timer.start(idx*1000, True)
		else:
			self.pvrstate_hide_timer.stop()
	elif self.execing and timeshiftEnabled and not self.isSeekable():
		self.pvrStateDialog.hide()


InfoBarTimeshiftState._mayShow = _mayShow

##################
# seekBack Hack  #
##################
InfoBarSeek_seekBack = InfoBarSeek.seekBack

def seekBack(self):
	InfoBarSeek_seekBack(self)
	self.pts_lastseekspeed = self.seekstate[1]

InfoBarSeek.seekBack = seekBack

def eventListPTS(self):
	if self.__class__.__name__ != "InfoBar":
			return
	if config.plugins.pts.long_record.value == "event":
		if config.plugins.pts.enabled.value and self.timeshift_enabled:
			InfoBar.saveTimeshiftEventPopup(self, view_only = True)
	else:
		if self.isInstantRecordRunning():
			serviceref = self.session.nav.getCurrentlyPlayingServiceReference()
			if isinstance(serviceref, ServiceReference):
				serviceref = serviceref.ref
			if len(self.recording) == 1 and self.recording[0].service_ref and self.recording[0].service_ref.ref == serviceref:
				self.stopCurrentRecording(0)
			else:
				self.instantRecord()
		else:
			dir = preferredInstantRecordPath()
			if not dir or not fileExists(dir, 'w'):
				dir = defaultMoviePath()
			try:
				stat = os_stat(dir)
			except:
				self.session.open(MessageBox, _("No HDD found or HDD not initialized!"), MessageBox.TYPE_ERROR)
				return
			self.recordQuestionCallback((_("add recording (indefinitely)"), "indefinitely"))

def ptsInfoBarInstantRecord__init__(self):
	self["InstantRecordActions"] = HelpableActionMap(self, "InfobarPTSRecord",
		{
			"instantRecord": (self.instantRecord, _("Instant recording...")),
			"eventList": (self.eventListPTS, _("start/stop instant record")),
		})
	self.SelectedInstantServiceRef = None
	if self.__class__.__name__ == "InfoBar":
		self.recording = []
	else:
		InfoBarInstance = InfoBarOrg.instance
		if InfoBarInstance:
			self.recording = InfoBarInstance.recording
	
InfoBarInstantRecord.__init__ = ptsInfoBarInstantRecord__init__
InfoBarInstantRecord.eventListPTS = eventListPTS

####################
#instantRecord Hack#
####################
InfoBarInstantRecord_instantRecord = InfoBarInstantRecord.instantRecord

def instantRecord(self, serviceRef=None):
	self.SelectedInstantServiceRef = serviceRef
	if self.__class__.__name__ != "InfoBar":
		InfoBarInstantRecord_instantRecord(self)
		return
	if not config.plugins.pts.enabled.value or not self.timeshift_enabled:
		InfoBarInstantRecord_instantRecord(self)
		return

	dir = preferredInstantRecordPath()
	if not dir or not fileExists(dir, 'w'):
		dir = defaultMoviePath()
	try:
		stat = os_stat(dir)
	except:
		self.session.open(MessageBox, _("No HDD found or HDD not initialized!"), MessageBox.TYPE_ERROR)
		return

	try:
		Timer_record = self.isTimerRecordRunning()
	except:
		Timer_record = False

	common =((_("Add recording (stop after current event)"), "event"),
	(_("Add recording (indefinitely)"), "indefinitely"),
	(_("Add recording (enter recording duration)"), "manualduration"),
	(_("Add recording (enter recording endtime)"), "manualendtime"),)
	if self.isInstantRecordRunning():
		title =_("A recording is currently running.\nWhat do you want to do?")
		list = ((_("Stop recording"), "stop"),) + common + \
		((_("Change recording (duration)"), "changeduration"),
		(_("Change recording (endtime)"), "changeendtime"),)
		if Timer_record:
			list += ((_("Stop timer recording"), "timer"),)
		list += ((_("Do nothing"), "no"),)
	else:
		title=_("Start recording?")
		list = common
		if Timer_record:
			list += ((_("Stop timer recording"), "timer"),)
		list += ((_("Do not record"), "no"),)
	if config.plugins.pts.save_filetimeshift.value:
		list = list + ((_("Timeshift")+" "+_("save recording (stop after current event)"), "saveTimeshift"),
		(_("Timeshift")+" "+_("save recording (Select event)"), "saveTimeshiftEvent"),
		(_("Timeshift")+" "+_("save recording (current event until this time)"), "saveCurrentTimeshift"))
	else:
		list = list + ((_("Timeshift")+" "+_("save recording (stop after current event)"), "saveTimeshift"),
		(_("Timeshift")+" "+_("save recording (Select event)"), "saveTimeshiftEvent"))
	self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox,title=title,list=list)

InfoBarInstantRecord.instantRecord = instantRecord

#############################
#recordQuestionCallback Hack#
#############################
InfoBarInstantRecord_recordQuestionCallback = InfoBarInstantRecord.recordQuestionCallback

def recordQuestionCallback(self, answer):
	InfoBarInstantRecord_recordQuestionCallback(self, answer)

	if config.plugins.pts.enabled.value:
		if answer is not None and answer[1] == "saveTimeshift":
			if InfoBarSeek.isSeekable(self) and self.pts_eventcount != self.pts_currplaying:
				InfoBar.SaveTimeshift(self, timeshiftfile="pts_livebuffer.%s" % self.pts_currplaying)
			else:
				Notifications.AddNotification(MessageBox,_("Timeshift will get saved at end of event!"), MessageBox.TYPE_INFO, timeout=5)
				self.save_current_timeshift = True
				config.plugins.pts.isRecording.value = True
		if answer is not None and answer[1] == "saveTimeshiftEvent":
			InfoBar.saveTimeshiftEventPopup(self)
		if answer is not None and answer[1] == "saveCurrentTimeshift":
			if self.save_current_timeshift:
				InfoBar.SaveCurrentTimeshiftPTS(self)
			else:
				InfoBar.CallbackSaveCurrentTimeshiftPTS(self, True)

		if answer is not None and answer[1].startswith("pts_livebuffer") is True:
			InfoBar.SaveTimeshift(self, timeshiftfile=answer[1])

InfoBarInstantRecord.recordQuestionCallback = recordQuestionCallback

############################
#####  SETTINGS SCREEN #####
############################
class PermanentTimeShiftSetup(Screen, ConfigListScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = [ "PTSSetup", "Setup" ]
		self.setup_title = _("Timeshift setup menu")

		self.onChangedEntry = [ ]
		self.list = [ ]
		ConfigListScreen.__init__(self, self.list, session = session, on_change = self.changedEntry)

		self["actions"] = ActionMap(["SetupActions", "ColorActions"],
		{
			"ok": self.SaveSettings,
			"green": self.SaveSettings,
			"red": self.Exit,
			"cancel": self.Exit
		}, -2)

		self["key_green"] = StaticText(_("OK"))
		self["key_red"] = StaticText(_("Cancel"))

		self.createSetup()
		self.onLayoutFinish.append(self.layoutFinished)
		self.prev_icon_mode = config.plugins.pts.icon_mode.value
		self.prev_z = config.plugins.pts.z.value
		self.prev_infobar_skin = config.plugins.pts.infobar_skin.value
		self.prev_icon_color = config.plugins.pts.icon_color.value

	def layoutFinished(self):
		self.setTitle(self.setup_title)

	def createSetup(self):
		self.list = [ getConfigListEntry(_("Activate permanent timeshift plugin"), config.plugins.pts.enabled) ]
		if config.plugins.pts.enabled.value:
			self.list.extend((
				getConfigListEntry(_("Timeshift mode"), config.plugins.pts.mode),
				getConfigListEntry(_("Timeshift max events"), config.plugins.pts.maxevents),
				getConfigListEntry(_("Timeshift max length event (min)"), config.plugins.pts.maxlength),
				getConfigListEntry(_("Timeshift duration for service without EPG (min)"), config.plugins.pts.length_no_epg),
				getConfigListEntry(_("Timeshift-save action on zap"), config.plugins.pts.favoriteSaveAction),
				getConfigListEntry(_("Show PTS Infobar while timeshifting"), config.plugins.pts.showinfobar)
			))
			if config.plugins.pts.showinfobar.value:
				self.list.append(getConfigListEntry(_("PTS infobar skin"), config.plugins.pts.infobar_skin))
			if config.plugins.pts.mode.value == "1":
				self.list.insert(2, getConfigListEntry(_("Behavior on start timeshift"), config.plugins.pts.manualmode))
			if config.plugins.pts.mode.value == "1":
				self.list.insert(3, getConfigListEntry(_("Timeshift start delay (wake device)"), config.plugins.pts.manual_startdelay))
			else:
				self.list.insert(4, getConfigListEntry(_("Permanent timeshift start delay (sec)"), config.plugins.pts.startdelay))
			if config.plugins.pts.mode.value == "0":
				self.list.insert(7, getConfigListEntry(_("Stop timeshift while recording"), config.plugins.pts.stopwhilerecording))
			self.list.append(getConfigListEntry(_("Behavior key long stop"), config.plugins.pts.long_stop))
			self.list.append(getConfigListEntry(_("Behavior key long record"), config.plugins.pts.long_record))
			self.list.append(getConfigListEntry(_("Add to save timeshift now in menu recording"), config.plugins.pts.save_filetimeshift))
			if config.plugins.pts.mode.value == "1":
				self.list.append(getConfigListEntry(_("Show warning on zap if not save action"), config.plugins.pts.check_timeshift))
			else:
				self.list.append(getConfigListEntry(_("Show warning on zap if not Live TV or not save action"), config.plugins.pts.check_timeshift))
				self.list.append(getConfigListEntry(_("Start timeshift for http stream"), config.plugins.pts.http_stream))
			self.list.append(getConfigListEntry(_("Show timeshift indicator in window"), config.plugins.pts.show_icon))
			if config.plugins.pts.show_icon.value:
				self.list.append(getConfigListEntry(_("Indicator mode"), config.plugins.pts.icon_mode))
				self.list.append(getConfigListEntry(_("Indicator color"), config.plugins.pts.icon_color))
				self.list.append(getConfigListEntry(_("X position (upper-left corner of srceen)"), config.plugins.pts.x))
				self.list.append(getConfigListEntry(_("Y position (upper-left corner of srceen)"), config.plugins.pts.y))
				self.list.append(getConfigListEntry(_("Z position (priority of srceen)"), config.plugins.pts.z))
		# Permanent Recording Hack
		if fileExists("/usr/lib/enigma2/python/Plugins/Extensions/HouseKeeping/plugin.py"):
			self.list.append(getConfigListEntry(_("Beta: Enable Permanent Recording?"), config.plugins.pts.permanentrecording))

		self["config"].list = self.list
		self["config"].setList(self.list)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		if self["config"].getCurrent()[1] == config.plugins.pts.enabled or (config.plugins.pts.enabled.value and self["config"].getCurrent()[1] == config.plugins.pts.mode) or (config.plugins.pts.enabled.value and self["config"].getCurrent()[1] == config.plugins.pts.showinfobar) or (config.plugins.pts.enabled.value and self["config"].getCurrent()[1] == config.plugins.pts.show_icon):
			self.createSetup()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		if self["config"].getCurrent()[1] == config.plugins.pts.enabled or (config.plugins.pts.enabled.value and self["config"].getCurrent()[1] == config.plugins.pts.mode)  or (config.plugins.pts.enabled.value and self["config"].getCurrent()[1] == config.plugins.pts.showinfobar) or (config.plugins.pts.enabled.value and self["config"].getCurrent()[1] == config.plugins.pts.show_icon):
			self.createSetup()

	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		return SetupSummary

	def SaveSettings(self):
		if config.plugins.pts.check_timeshift.value:
			try:
				config.usage.check_timeshift.setValue(True)
				config.usage.check_timeshift.save()
			except:
				pass
		if config.plugins.pts.enabled.value:
			try:
				config.usage.timeshift_start_delay.value = 0
				config.usage.timeshift_start_delay.save()
			except:
				pass
		if config.plugins.pts.length_no_epg.value >= config.plugins.pts.maxlength.value:
			self.session.open(MessageBox, _("Duration for service without EPG more time than max length event!\nPlease change the settings!"), MessageBox.TYPE_INFO, timeout = 5)
			return
		if self.prev_z != config.plugins.pts.z.value or self.prev_infobar_skin != config.plugins.pts.infobar_skin.value:
			self.session.open(MessageBox, _("To apply this settings (Z position or PTS infobar skin), you need a restart GUI!"), MessageBox.TYPE_INFO, timeout = 5)
		if self.prev_icon_mode != config.plugins.pts.icon_mode.value and config.plugins.pts.show_icon.value or self.prev_icon_color != config.plugins.pts.icon_color.value:
			config.plugins.pts.show_icon.value = False
			config.plugins.pts.show_icon.value = True
		config.plugins.pts.save()
		configfile.save()
		self.close()

	def Exit(self):
		for x in self["config"].list:
			x[1].cancel()
		self.close()

#################################################
def main(session, **kwargs):
	session.open(PermanentTimeShiftSetup)

def startSetup(menuid):
	if menuid != "system":
		return [ ]
	return [(_("Permanent Timeshift"), PTSSetupMenu, "pts_setup", 50)]

def PTSSetupMenu(session, **kwargs):
	session.open(PermanentTimeShiftSetup)

def Plugins(path, **kwargs):
	return [
				PluginDescriptor(name=_("Permanent Timeshift Settings"), description=_("Permanent Timeshift Settings"), where=PluginDescriptor.WHERE_MENU, fnc=startSetup ),
				PluginDescriptor(name=_("Permanent Timeshift"), description=_("Permanent Timeshift settings"), where=PluginDescriptor.WHERE_PLUGINMENU, fnc=main ),  
				]
