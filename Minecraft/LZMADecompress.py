#!/usr/bin/env python
#
# Copyright 2013 Nick McSpadden
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This Python-only LZMA decompression is copied wholesale from Mike Lynn's
# excellent xz_decompress.py tool, posted here: 
# https://gist.github.com/pudquick/9f9023f8e9b1a9af53d0

from autopkglib import Processor, ProcessorError

import os.path
import sys
from ctypes import CDLL, Structure, c_void_p, c_size_t, c_uint, c_uint32, c_uint64, create_string_buffer, addressof, sizeof, byref

class lzma_stream(Structure):
    _fields_ = [
        ("next_in",        c_void_p),
        ("avail_in",       c_size_t),
        ("total_in",       c_uint64),
        ("next_out",       c_void_p),
        ("avail_out",      c_size_t),
        ("total_out",      c_uint64),
        ("allocator",      c_void_p),
        ("internal",       c_void_p),
        ("reserved_ptr1",  c_void_p),
        ("reserved_ptr2",  c_void_p),
        ("reserved_ptr3",  c_void_p),
        ("reserved_ptr4",  c_void_p),
        ("reserved_int1",  c_uint64),
        ("reserved_int2",  c_uint64),
        ("reserved_int3",  c_size_t),
        ("reserved_int4",  c_size_t),
        ("reserved_enum1", c_uint),
        ("reserved_enum2", c_uint),
    ]

# Hardcoded this path to the System liblzma dylib location, so that /usr/local/lib or other user
# installed library locations aren't used (which ctypes.util.find_library(...) would hit).
# Available in OS X 10.7+
c_liblzma = CDLL('/usr/lib/liblzma.dylib')

NULL               = None
BUFSIZ             = 4096
LZMA_OK            = 0
LZMA_RUN           = 0
LZMA_FINISH        = 3
LZMA_STREAM_END    = 1
BLANK_BUF          = '\x00'*BUFSIZ
UINT64_MAX         = c_uint64(18446744073709551615)
LZMA_CONCATENATED  = c_uint32(0x08)
LZMA_RESERVED_ENUM = 0
LZMA_STREAM_INIT   = [NULL, 0, 0, NULL, 0, 0, NULL, NULL, NULL, NULL, NULL, NULL, 0, 0, 0, 0, LZMA_RESERVED_ENUM, LZMA_RESERVED_ENUM]


__all__ = ["LZMADecompress"]

class LZMADecompress(Processor):
	description = "Decompresses an LZMA file."
	input_variables = {
		"lzma_file": {
			"required": True,
			"description": "Path to .lzma file.",
		},
		"decompressed_path": {
			"required": False,
			"description": ("Path to output decompressed file.  Defaults to",
							"%RECIPE_CACHE_DIR% with filename of input file, minus extension.",
							"If file exists, it will be overwritten."),
		}
	}
	output_variables = {
	}

	__doc__ = description

	def decompress(self, infile, outfile):
		# Create an empty lzma_stream object
		strm = lzma_stream(*LZMA_STREAM_INIT)
	
		# Initialize a decoder
		result = c_liblzma.lzma_alone_decoder(byref(strm), UINT64_MAX, 0)
	
		# Setup the output buffer
		outbuf = create_string_buffer(BUFSIZ)
		strm.next_out  = addressof(outbuf)
		strm.avail_out = sizeof(outbuf)
	
		# Setup the (blank) input buffer
		inbuf  = create_string_buffer(BUFSIZ)
		strm.next_in = addressof(inbuf)
		strm.avail_in = 0
	
		# Read in the input .xz file
		# ... Not the best way to do things because it reads in the entire file - probably not great for GB+ size
		f_in = open(infile, 'rb')
		xz_file = f_in.read()
		f_in.close()
	
		cursor = 0
		EOF = len(xz_file)
	
		# Open up our output file
		f_out = open(outfile, 'wb')
	
		# Start with a RUN action
		action = LZMA_RUN
		# Keep looping while we're processing
		while True:
			# Check if decoder has consumed the current input buffer and we have remaining data
			if ((strm.avail_in == 0) and (cursor < EOF)):
				# Load more data!
				# In theory, I shouldn't have to clear the input buffer, but I'm paranoid
				inbuf[:] = BLANK_BUF
				# Now we load it:
				# - Attempt to take a BUFSIZ chunk of data
				input_chunk = xz_file[cursor:cursor+BUFSIZ]
				# - Measure how much we actually got
				input_len   = len(input_chunk)
				# - Assign the data to the buffer
				inbuf[0:input_len] = input_chunk
				# - Configure our chunk input information
				strm.next_in  = addressof(inbuf)
				strm.avail_in = input_len
				# - Adjust our cursor
				cursor += input_len
				# - If the cursor is at the end, switch to FINISH action
				if (cursor >= EOF):
					action = LZMA_FINISH
			# If we're here, we haven't completed/failed, so process more data!
			result = c_liblzma.lzma_code(byref(strm), action)
			# Check if we filled up the output buffer / completed running
			if ((strm.avail_out == 0) or (result == LZMA_STREAM_END)):
				# Write out what data we have!
				# - Measure how much we got
				output_len   = BUFSIZ - strm.avail_out
				# - Get that much from the buffer
				output_chunk = outbuf.raw[:output_len]
				# - Write it out
				f_out.write(output_chunk)
				# - Reset output information to a full available buffer
				# (Intentionally not clearing the output buffer here .. but probably could?)
				strm.next_out  = addressof(outbuf)
				strm.avail_out = sizeof(outbuf)
			if (result != LZMA_OK):
				if (result == LZMA_STREAM_END):
					# Yay, we finished
					result = c_liblzma.lzma_end(byref(strm))
					return True
				# If we got here, we have a problem
				# Error codes are defined in xz/src/liblzma/api/lzma/base.h (LZMA_MEM_ERROR, etc.)
				# Implementation of pretty English error messages is an exercise left to the reader ;)
				raise Exception("Error: return code of value %s - naive decoder couldn't handle input!" % (result))


	def main(self):
		'''Does nothing except decompresses the file'''
		if not os.path.isfile(self.env["lzma_file"]):
			raise ProcessorError("No valid LZMA file at path %s" % self.env["lzma_file"])
		self.output("Using input LZMA file %s" % self.env["lzma_file"])
		if "decompressed_path" in self.env:
			output_file = self.env["decompressed_path"]
		else:
			output_file = os.path.join(self.env.get('RECIPE_CACHE_DIR'), os.path.splitext(os.path.basename(self.env["lzma_file"]))[0])
		# if the file already exists, delete it.
		if os.path.isfile(output_file):
			self.output("Decompressed file already exists, deleting: %s" % output_file)
			os.remove(output_file)
		self.output("Decompressing to %s" % output_file)
		self.decompress(self.env["lzma_file"], output_file)
		self.output("Decompressed.")


if __name__ == '__main__':
    processor = LZMADecompress()
    processor.execute_shell()
    

