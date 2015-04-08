#!/bin/sh

#VerifyMinecraft

mcpath="/Library/Application Support/minecraft/"
homepath="$HOME/Library/Application Support/"
endpath="$HOME/Library/Application Support/minecraft/"
#the rsync command below will not behave as expected if the trailing slashes are missing!

if [[ -e "$mcpath" ]]
then
	/usr/bin/rsync -rtuc "$mcpath" "$endpath"
	#r - recursive
	#t - preserve modification dates
	#u - update the folder, don't copy unchanged files
	#c - calculate checksum of each file to determine if it's changed
	chown -R $USER:staff "$endpath"
else
	echo "Didn't find Minecraft in /Library/Application Support/."
	exit 1
fi
