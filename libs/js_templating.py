##########################################
#
# Rainwave Templating System
#
# This is a very simple templating system that will output
# native Javascript DOM calls and functions attached
# to a global JS variable called RWTemplates.
#
# Also mucks with having shorthand versions of native
# functions for minification, so careful if you're also
# calling things as Element.prototype.(s|a) and document.c.
#
# Cannot deal with SVG except for Rainwave's particular use case.
#
# It looks much like Handlebars, except you have no helpers system.
# The only big restriction is that {{#each}} cannot handle
# objects - only arrays.
#
# Some handy things to know:
#
#	{{ @root.blah }}
#   	 - access root context object
# 	{{ $blahblah }}
#   	 - use raw JS including $ (this is a dumb hack for Rainwave)
# 	{{ ^blahblah }}
#   	 - use raw JS output excluding ^
#
# This system is very dumb.  But it's fast in the browser.
# Seriously.  Stupid fast.
#
##########################################

import re
from HTMLParser import HTMLParser

_unique_id_chars = [ chr(x) for x in xrange(65, 91) ] + [ chr(x) for x in xrange(97, 123) ]
_unique_id = _unique_id_chars[0]
def _get_id():
	global _unique_id
	next_idx = _unique_id_chars.index(_unique_id[-1]) + 1
	if next_idx >= len(_unique_id_chars):
		_unique_id += _unique_id_chars[0]
		return _unique_id
	_unique_id = _unique_id[:-1] + _unique_id_chars[next_idx]
	return _unique_id

def js_start():
	return ("(function(){"
		"var d=document;"
		"d.c=d.createElement;"
		"Element.prototype.s=Element.prototype.setAttribute;"
		"Element.prototype.a=Element.prototype.appendChild;"
		"function $svg_icon(icon, cls){"
			"\"use strict\";"
			"var s=document.createElementNS(\"http://www.w3.org/2000/svg\", \"svg\");"
			"var u=document.createElementNS(\"http://www.w3.org/2000/svg\", \"use\");"
			"use.setAttributeNS(\"http://www.w3.org/1999/xlink\", \"xlink:href\", \"/static/images4/symbols.svg#\" + icon);"
			"if (cls) {"
				"svg.setAttributeNS(null, \"class\", cls);"
			"}"
			"svg.appendChild(use);"
			"return svg;"
		"}"
		"window.RWTemplates={")

def js_end():
	return "};})();"

class RainwaveParser(HTMLParser):
	tree = [ ]
	stack = [ ]
	tree_names = [ ]
	buffr = None
	name = None

	def parse_context_key(self, context_key):
		if context_key[0:6] == "@root.":
			return "_b.%s" % context_key[6:]
		if context_key[0] == "$":
			return context_key
		if context_key[0] == "^":
			return context_key[1:]
		else:
			return "_c.%s" % context_key

	def _parse_val(self, val):
		use_plus = False
		final_val = ""
		for m in re.split(r"({{.*?}})", val):
			tm = None
			if m[:2] == "{{" and m[-2:] == "}}":
				tm = self.parse_context_key(m[2:-2].strip())
			elif len(m.strip()) > 0:
				tm = "\"%s\"" % m
			if tm:
				if use_plus:
					final_val += "+"
				final_val += tm
				use_plus = True
		return final_val

	def __init__(self, template_name, *args, **kwargs):
		global _unique_id
		global _unique_id_chars

		HTMLParser.__init__(self, *args, **kwargs)
		_unique_id = _unique_id_chars[0]
		self.name = template_name
		self.buffr =  "%s:function(_c){" % template_name
		self.buffr += "\"use strict\";"
		self.buffr += "_c=_c||{};"
		self.buffr += "if(!_c.$t)_c.$t={};"
		self.buffr += "var _b=_c;" # don't know what else I can call the root context
		self.buffr += "if(!_c.$t.root)_c.$t.documentFragment=d.createDocumentFragment();"
		self.buffr += "var _r=_c.$t.documentFragment;"
		# I've tried modifying the documentFragment prototype.  Browsers don't like that. :)
		# So we do a bit of function-copying here in the JS.
		self.buffr += "_r.a=_r.appendChild;"

	def close(self, *args, **kwargs):
		HTMLParser.close(self, *args, **kwargs)
		if len(self.stack):
			raise Exception("%s unclosed stack: %s" % (self.name, repr(self.stack)))
		if len(self.tree):
			raise Exception("%s unclosed tags: %s" % (self.name, repr(self.tree_names)))
		self.buffr += "return _c;"
		self.buffr += "}"
		return self.buffr

	def handle_starttag(self, tag, attrs):
		uid = _get_id()

		if tag == "svg":
			svg_use = None
			svg_cls = "null"
			for attr in attrs:
				if attr[0] == "use":
					svg_use = self._parse_val(attr[1])
				elif attr[0] == "class":
					svg_cls = self._parse_val(attr[1])
			if svg_use:
				self.buffr += "var %s=$svg_icon(%s, %s)" % (uid, svg_use, svg_cls)
			else:
				raise Exception("(%s) The Rainwave templater cannot support SVG unless in this format: <svg use=\"icon_id\" class=\"cls\">" % self.name)
		else:
			self.buffr += "var %s=d.c('%s');" % (uid, tag)
		self.handle_append(uid)
		self.tree.append(uid)
		self.tree_names.append((tag, attrs))
		if not tag == "svg":
			for attr in attrs:
				attr_val = self._parse_val(attr[1])
				if attr[0] == "bind":
					self.buffr += "_c.$t.%s=%s;" % (attr_val.strip('"'), uid)
				else:
					self.buffr += "%s.s('%s',%s);" % (uid, attr[0], attr_val)

	def handle_append(self, uid):
		if len(self.tree) == 0:
			self.buffr += "_r.a(%s);" % uid
		else:
			self.buffr += "%s.a(%s);" % (self.tree[-1], uid)

	def handle_endtag(self, tag):
		try:
			self.tree.pop()
			self.tree_names.pop()
		except IndexError:
			raise Exception("%s has too many closing tags." % self.name)

	def handle_data(self, lines):
		if not lines:
			return
		for line in re.split(r"({{.*?}})", lines):
			data = line.strip()
			if not data or len(data) == 0:
				pass
			elif data[:3] == "{{>" and data[-2:] == "}}":
				self.handle_subtemplate(data[3:-2])
			elif data[:3] == "{{#" and data[-2:] == "}}":
				self.handle_stack_push(data[3:-2])
			elif data[:3] == "{{/" and data[-2:] == "}}":
				self.handle_stack_pop(data[3:-2])
			elif not len(self.tree):
				raise Exception("%s: Tried to set textContent of root element.  Put text in an element. (\"%s\")" % (self.name, data))
			else:
				self.buffr += "%s.textContent+=%s;" % (self.tree[-1], self._parse_val(data))

	def handle_stack_push(self, data):
		args = data.strip().split(' ', 1)
		entry = { "name": args[0] }
		if len(args) > 1:
			entry['argument'] = args[1]

		# This quickly closes the 'if' tag itself and copies the arguments over to 'else'
		if len(self.stack) and self.stack[-1]['name'] == "if" and data == "else":
			entry = self.stack[-1]
			self.handle_stack_pop(entry['name'])
			entry['name'] = "else"

		entry['function_id'] = _get_id()
		self.buffr += "var %s=function(_c){" % entry['function_id']
		self.stack.append(entry)

	def handle_stack_pop(self, name):
		if not len(self.stack):
			raise Exception("Closing tag %s exists where there are no opening tags in %s template." % (name, self.name))
		# break on mismatched tags unless we're just closing an else to an if
		if not name == self.stack[-1]['name'] and not (name == "if" and self.stack[-1]['name'] == "else"):
			raise Exception("Mismatched open and close tags (%s and %s) in %s template." % (self.stack[-1]['name'], name, self.name))

		self.buffr += "};"
		getattr(self, "handle_%s" % self.stack[-1]['name'])(self.stack[-1]['function_id'], self.stack[-1]['argument'])
		self.stack.pop()

	def handle_each(self, function_id, context_key):
		context_key = self.parse_context_key(context_key)
		self.buffr += "for(var i= 0;i<%s.length;i++){" % context_key
		self.buffr += "if(!%s[i].$t)%s[i].$t={};" % (context_key, context_key)
		self.buffr += "%s(%s[i]);" % (function_id, context_key)
		self.buffr += "}"

	def handle_subtemplate(self, template_name):
		self.handle_append("RWTemplates.%s(_c)" % template_name)

	def handle_if(self, function_id, context_key):
		context_key = self.parse_context_key(context_key)
		self.buffr += "if(%s)%s(_c);" % (context_key, function_id)

	def handle_else(self, function_id, context_key):
		context_key = self.parse_context_key(context_key)
		self.buffr += "if(!(%s))%s(_c);" % (context_key, function_id)

	def handle_with(self, function_id, context_key):
		context_key = self.parse_context_key(context_key)
		self.buffr += "%s(%s);" % (function_id, context_key)