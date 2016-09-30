This is a bot to use in your Tinychat room,<br/>
This is using the pinylib library by @nortxort,<br/>
You'll need all the dependencies for this to work,<br/>
You can install the modules directly in your python library or run them from the bot folder,<br/>
Just make sure you have [Python 2.7](https://www.python.org/downloads/) installed.

Please check the <a href="https://github.com/Tinychat/Tinychat-Bot/wiki">Wiki</a> for list of commands.

This has fixes from the old bot and inprovements,<br/>
Moderators cannot ban another Moderator (I wasn't aware of this until a user (`Jesus`) informed me.)<br/>
Moderators now have better controls over the room for when the super user is not available,<br/>
Some of which are `op`, `deop`, `guests`, `guestnicks`, `badnicks`,`badaccounts` without the need for a key<br/>
This is of benifit for where the super user is not available.

##Windows
`C:\Python27\Scripts\pip2 install bf4 pyamf requests colorama goslate` or

`cd c:\Extracted folders directory\ python setup.py install` or

open command prompt or Powershell and type `pip install bf4 pyamf requests colorama goslate`

##Linux
Open the terminal and type

`pip2 install bf4 pyamf requests colorama goslate`

##Mac
Open the terminal and type

`sudo easy_install pip` then

`pip install bf4 pyamf requests colorama goslate`

##Help running Python and pip from inside command prompt or windows shell.
###To be able to run `pip` inside command prompt on Windows use the below info,<br/>
Open start, locate control panel and open it, click `System and Security`,<br/>
Then click `System`, on the Right click `Advanced system settings`,<br/>
Then click `Environment Variables`, In the System variables box scroll to Path and double click it,<br/>
It will open a box, Click `Edit` or `New` depending on your version of Windows,<br/>
Now type in (Windows 8 - 10) `C:\Python27\` and after the last value type in a `;` <br/>
now type `C:\Python27\;C:\Python27;Scripts\;` for (Windows 7 or below) Click Ok<br/>
Now open Command Prompt or Shell and type in `python` and click Enter it should now open python in the window,<br/>
Now you can run pip directly inside command prompt, `pip install bf4 pyamf requests colorama goslate`,<br/>
If this still isn't working for you, Please contact me for help.
