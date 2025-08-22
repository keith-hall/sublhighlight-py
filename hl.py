#!/usr/bin/env python3
# tip: use with '| less -r'

import argparse
import os
import onigurumacffi as oniguruma
import regex as re
import sys
from io import StringIO
from math import (
	floor,
	ceil,
)
from scsast import scorexp
from sublcolorscheme import (
	loadcolorscheme,
	parsecolorscheme,
	file_ext as sublcolscheme_ext,
	color_scheme_dir_path,
	all_color_schemes_names,
)
from sublcolorsys import (
	rgba_to_ansi256,
	hlsa_to_rgba,
	rgba_to_hlsa,
	hlsa_lerp,
	term_color,
)
from sublsyntax import (
	loadsyntax,
	loadsyntaxesmp,
	parsesyntax,
	ctx_findprop,
	file_ext as sublsynt_ext,
	syntax_dir_path,
	all_syntaxes_names,
	all_syntaxes_paths,
	loadsyntax_until,
)


class RuntimeContext:

	def __init__(
		self,
		syntax,
		key,
		actionlist,
		included:bool,
		with_prototype,
		embed
	):
		self.syntax = syntax
		self.name = key if isinstance(key, str) else str(key)
		self.actionlist = actionlist
		self.lenactionlist = len(actionlist)
		self.curr_action_id = 0
		self.included = included
		self.metascope = None
		self.meta_content_scope = None
		self.branch_meta = None
		self.with_prototype = with_prototype
		self.embed = embed

	def __str__(self):
		return f"{self.name} included: {self.included} metascope: {self.metascope} meta_content_scope: {self.meta_content_scope} branch_meta: {'yes' if self.branch_meta else 'no'} syntax: {self.syntax['name']}"


class BranchMetadata:

	def __init__(self, ctx_id, branch_point, branches_iter, prev_text, prev_pos, prev_io):
		self.ctx_id = ctx_id
		self.branch_point = branch_point
		self.branches_iter = branches_iter
		self.prev_text = StringIO()
		self.prev_text.write(prev_text)
		self.prev_pos = prev_pos
		self.prev_io = prev_io

	def __str__(self):
		return f"branch_point: {self.branch_point} prev_pos: {self.prev_pos}"

	def rollback(self):
		return (
			self.prev_pos,
			self.prev_text.getvalue(),
			self.prev_io
		)


class WithPrototype:

	def __init__(self, context, syntax):
		self.context = context
		self.syntax = syntax


class Embed:

	def __init__(self, escape_pattern, rollback_id, content_scope, captures):
		self.escape_pattern = escape_pattern
		self.rollback_id = rollback_id
		self.content_scope = content_scope
		self.captures = captures


class SyntaxHighlighter:

	def __init__(
		self,
		syntax:dict,
		color_scheme:dict,
		io,
		show_scopes:bool=False
	):
		self.contextstack = []
		self.main_syntax = syntax
		self.syntaxes_by_scope = {}
		self.color_scheme = color_scheme
		self.io = io
		self.scopestack = []
		self.scopepops = []
		self.show_scopes = show_scopes
		self.cache_scope_to_syntax_map(syntax)
		
	def load_syntax_lazy(self, path : str):
		return parsesyntax(
			loadsyntax(path),
			self.cache_scope_to_syntax_map
		)

	def cache_scope_to_syntax_map(self, syntax):
		self.syntaxes_by_scope[syntax["scope"]] = syntax

	def load_syntax_lazy_with_scope(self, syntax_scope : str):
		if syntax_scope in self.syntaxes_by_scope:
			return self.syntaxes_by_scope[syntax_scope]
		scope_regex = re.compile(fr"^scope:[ ]*{syntax_scope}", re.IGNORECASE)
		for path in all_syntaxes_paths:
			with open(path, "r", encoding="latin1") as f:
				for line in f:
					if scope_regex.match(line):
						return self.load_syntax_lazy(path)

	token_color_cache = {}

	def token_color(self, token:str):
		scopestack = self.scopestack
		cache_key = hash((*(y for x in scopestack for y in x), token))
		if cache_key in self.token_color_cache:
			if dbg: dbg(f"token_color: token: {repr(token)} cached: {self.token_color_cache[cache_key]}")
			return self.token_color_cache[cache_key]
		_globals = self.color_scheme["globals"]
		rules = self.color_scheme["rules"]
		best = None
		best_score = 0
		lenss = len(scopestack)
		if dbg: dbg(f"token_color: token: {repr(token)} ss: {scopestack}")
		for rule in rules:
			xp = rule["scope"]
			score = scorexp(
				xp,
				scopestack,
				lenss
			)
			if score > 0 and (best is None or score > best_score):
				best = rule
				best_score = score
		if best is not None:
			foreground = best.get("foreground", _globals["foreground"])
			if dbg: dbg(f"token_color: token: {repr(token)} best rule: {best} has gradient: {'yes' if isinstance(foreground, list) else 'no'}")
			if isinstance(foreground, list):
				color_t = hash(token) % 255 / 255 if token else 0.0
				samp_t = color_t * len(foreground) - color_t
				foreground = hlsa_to_rgba(
					*hlsa_lerp(
						rgba_to_hlsa(*foreground[int(floor(samp_t))]),
						rgba_to_hlsa(*foreground[int(ceil(samp_t))]),
						color_t
					)
				)
				if dbg: dbg(f"token_color: token: {repr(token)} color_t: {color_t} samp_t: {samp_t} color: {foreground}")
			entry = (
				rgba_to_ansi256(*foreground),
				rgba_to_ansi256(*best.get("background", _globals["background"]))
			)
			self.token_color_cache[cache_key] = entry
			return entry
		else:
			if dbg: dbg(f"no matching rule for token: {repr(token)}")
		entry = rgba_to_ansi256(*_globals["foreground"]), rgba_to_ansi256(*_globals["background"])
		self.token_color_cache[cache_key] = entry
		return entry

	def push_scope(self, scopes:str):
		scopes = scopes.split(" ")
		self.scopepops.append(len(scopes))
		for scope in scopes:
			self.scopestack.append(scope.split("."))
			token_color = self.token_color(None)
			if dbg: dbg(f"push_scope: {scope} color: {token_color}")
			self.io.write(term_color(*token_color))
			if self.show_scopes:
				self.io.write(f"<{scope}>")
		
	def pop_scope(self):
		npops = self.scopepops.pop()
		for i in range(npops):
			rtscope = self.scopestack.pop()
			if self.show_scopes:
				self.io.write(f"</{'.'.join(rtscope)}>")
			token_color = self.token_color(None)
			if dbg: dbg(f"pop_scope: {rtscope} color: {token_color}")
			self.io.write(term_color(*token_color))

	def write_token(self, token:str):
		token_color = self.token_color(token)
		if dbg: dbg(f"write_token: {repr(token)} color: {token_color}")
		self.io.write(term_color(*token_color))
		self.io.write(token)

	@property
	def context(self):
		return self.contextstack[-1] if self.contextstack else None

	@property
	def ctx_syntax(self):
		return self.contextstack[-1].syntax if self.contextstack else self.main_syntax

	def get_context(self, syntax:dict, key):
		if isinstance(key, str):
			return syntax["contexts"].get(key, None)
		return key # anonymous context

	re_pushref = re.compile(r"scope:([^#]+)(?:#(.+))?")

	def push_context(
		self,
		key,
		included:bool=False,
		syntax=None,
		do_metascope=True,
		with_prototype=None,
		embed=None
	):
		if syntax is None:
			syntax = self.ctx_syntax
		if isinstance(key, list) and not any(map(lambda x:isinstance(x, dict), key)):
			# important: retain this context syntax to avoid problems with mixed syntaxes from prototypes
			for k in key:
				self.push_context(
					k,
					included=included,
					syntax=syntax,
					do_metascope=do_metascope,
					with_prototype=with_prototype
				)
			return
		if isinstance(key, str):
			if key.startswith("scope:"):
				pushref = self.re_pushref.match(key)
				if not pushref:
					raise ValueError(f"push_context: push reference has an invalid format, expecting scope:.+(#.+)? got: {key}")
				extscope, key = pushref.groups()
				if not key:
					key = "main"
				syntax = self.load_syntax_lazy_with_scope(extscope)
				if not syntax:
					raise KeyError(f"push_context: external syntax (by scope): {extscope} not found, are you missing a syntax file?")
			elif key.startswith("packages/"): #hacky
				mapped_path = os.path.join(
					syntax_dir_path,
					os.path.basename(key)
				)
				syntax = self.load_syntax_lazy(mapped_path)
				if not syntax:
					raise KeyError(f"push_context: external syntax: '{mapped_path}' not found, are you missing a syntax file?")
				key = "main"
		ctx = self.get_context(syntax, key)
		if ctx is not None:
			if with_prototype is None:
				with_prototype = self.contextstack[-1].with_prototype if self.contextstack else None
			if embed is None:
				embed = self.contextstack[-1].embed if self.contextstack else None
			rtctx = RuntimeContext(syntax, key, ctx, included, with_prototype, embed)
			if not included:
				clear_scopes = ctx_findprop(ctx, "clear_scopes", None)
				if clear_scopes:
					ctxstack_len = len(self.contextstack)
					n = ctxstack_len if clear_scopes is True else clear_scopes
					if dbg: dbg(f"clear_scopes: n: {n}")
					i = ctxstack_len - 1
					while i >= 0 and n > 0:
						clrctx =  self.contextstack[i]
						if not clrctx.included:
							if dbg: dbg(f"clear_scopes: clearing: {clrctx.name} i: {i}")
							if clrctx.meta_content_scope:
								self.pop_scope()
								clrctx.meta_content_scope = None
							if clrctx.metascope:
								self.pop_scope()
								clrctx.metascope = None
							n -= 1
						i -= 1
				metascope = ctx_findprop(ctx, "meta_scope", None)
				if metascope:
					rtctx.metascope = metascope
					if do_metascope:
						self.push_scope(metascope)
				meta_content_scope = ctx_findprop(ctx, "meta_content_scope", None)
				if meta_content_scope:
					rtctx.meta_content_scope = meta_content_scope
					self.push_scope(meta_content_scope)
			# if dbg: dbg(f"push_context: {rtctx}")
			self.contextstack.append(rtctx)
			if dbg: dbg("push:" + " <- ".join(map(lambda x:f"{x.name}{'(inc)' if x.included else ''}{'(branch)' if x.branch_meta else ''}{'(embed)' if x.embed else ''}({x.syntax['name']})", reversed(self.contextstack))))
			if not included and key != "prototype":
				self.reset_context(rtctx)
		elif key != "prototype":
			raise KeyError(f"push_context: context: {key} not found; ctx: {self.contextstack[-1]}")

	def pop_context(self, handle_branching=True):
		if dbg: dbg("pop:" + " <- ".join(map(lambda x:f"{x.name}{'(inc)' if x.included else ''}{'(branch)' if x.branch_meta else ''}{'(embed)' if x.embed else ''}({x.syntax['name']})", reversed(self.contextstack))))
		rtctx = self.contextstack.pop()
		# if dbg: dbg(f"pop_context: {rtctx}")
		if not rtctx.included:
			if rtctx.meta_content_scope:
				self.pop_scope()
				rtctx.meta_content_scope = None
			if rtctx.metascope:
				self.pop_scope()
				rtctx.metascope = None
		if handle_branching and self.contextstack:
			nextctx = self.contextstack[-1]
			if nextctx.branch_meta:
				if dbg: dbg(f"BRANCH success: branch: {rtctx.name} of {nextctx.branch_meta.branch_point} @ {nextctx.name}")
				prev_io = nextctx.branch_meta.prev_io
				prev_io.write(self.io.getvalue())
				self.io.close()
				self.io = prev_io
				nextctx.branch_meta = None
		assert rtctx.branch_meta == None
		return rtctx

	def reset_context(self, rtctx):
		if rtctx.included:
			raise Exception(f"cannot reset_context: {rtctx}")
		rtctx.curr_action_id = 0
		if dbg: dbg(f"reset_context: {rtctx}")
		if rtctx.name != "prototype":
			if rtctx.with_prototype:
				assert rtctx.with_prototype.context
				self.push_context(rtctx.with_prototype.context, included=True, syntax=rtctx.with_prototype.syntax)
			if not any(map(lambda x:not x.get("meta_include_prototype", True), rtctx.actionlist)):
				self.push_context("prototype", included=True)

	re_varsub = re.compile(r"{{([A-Za-z0-9_]+)}}")

	def compile_pattern(self, patt, rtctx):
		# if dbg: dbg(f"compiling pattern: {patt}")
		opatt = patt
		while True:
			varnames = self.re_varsub.findall(patt)
			if not varnames:
				break
			for varname in varnames:
				var = rtctx.syntax["variables"].get(varname, None)
				if var:
					patt = patt.replace(f"{{{{{varname}}}}}", var, 1)
				else:
					raise KeyError(f"variable: {varname} not found")
		try:
			return oniguruma.compile(patt)
		except Exception:
			print(f"errors compiling pattern: {opatt} => {patt}")
			raise

	def begin(self):
		assert len(self.contextstack) == 0
		self.push_context("main")
		rtctx = self.contextstack[-1]
		scope = rtctx.syntax.get("scope", None)
		rtctx.metascope = scope
		if scope:
			self.push_scope(scope)

	def process(self, text:str, pos:int=0):
		if dbg: dbg(f"init ANALYZE pos: {pos} text: {repr(text[pos:pos + 8])}...")
		for ctx in self.contextstack:
			if ctx.branch_meta:
				ctx.branch_meta.prev_text.write(text)
		while pos < len(text):
			rtctx = self.contextstack[-1]
			rtctx_curr_action_id = rtctx.curr_action_id
			if rtctx_curr_action_id == 0 and rtctx.embed:
				didRollback, text, pos = self.match_embed_and_rollback(rtctx, text, pos)
				if didRollback:
					continue
			if rtctx_curr_action_id >= rtctx.lenactionlist:
				if rtctx.included:
					self.pop_context()
					continue
				self.io.write(text[pos])
				pos += 1
				self.reset_context(rtctx)
				if dbg and pos < len(text): dbg(f"loop ANALYZE pos: {pos} text: {repr(text[pos:pos + 8])}...")
				continue
			actiondef = rtctx.actionlist[rtctx_curr_action_id]
			rtctx.curr_action_id = rtctx_curr_action_id + 1
			opos = pos
			action = next(iter(actiondef))
			if action == "match":
				pos, text = self.action_match(rtctx, text, pos, actiondef)
			elif action == "include":
				self.push_context(actiondef["include"], included=True)
			if dbg and opos != pos:
				dbg(f"step ANALYZE pos: {pos} text: {repr(text[pos:pos + 8])}...")
		return text

	def end(self):
		while self.contextstack:
			self.pop_context()

	def action_match(self, rtctx, text:str, pos:int, actiondef:dict):
		patt = actiondef["match"]
		if isinstance(patt, str):
			pattern = patt
			patt = self.compile_pattern(patt, rtctx)
			patt.pattern = patt
			actiondef["match"] = patt
		match = patt.match(text, pos)
		if match:
			scope = actiondef.get("scope", None)
			captures = actiondef.get("captures", None)
			push = actiondef.get("push", None)
			pop = actiondef.get("pop", None)
			_set = actiondef.get("set", None)
			branch = actiondef.get("branch", None)
			fail = actiondef.get("fail", None)
			embed = actiondef.get("embed", None)
			with_prototype = actiondef.get("with_prototype", None)
			with_prototype = WithPrototype(with_prototype, rtctx.syntax) if with_prototype else None
			if _set:
				pop = 1
				push = _set
			if embed:
				push = embed
				try:
					embed_escape = actiondef["escape"]
				except KeyError:
					raise KeyError(f"embed_escape is required when specifying and embed. ctx: {rtctx}")
				try:
					gi = 0
					while True:
						#fix-me: syntax-blind replace, but at least it works in usual cases
						if match.group(gi):
							embed_escape = re.sub(f"(?<=\\b)\\\\{gi}(?=\\b)", match.group(gi), embed_escape)
						gi += 1
				except IndexError:
					pass
				if isinstance(embed_escape, str):
					embed_escape = self.compile_pattern(embed_escape, rtctx)
					actiondef["escape"] = embed_escape
				try:
					revid, itm = next(filter(lambda x:not x[1].included, enumerate(reversed(self.contextstack))))
					rollback_id = len(self.contextstack) - revid - 1
				except StopIteration:
					rollback_id = len(self.contextstack) - 1
				embed = Embed(
					embed_escape,
					rollback_id,
					actiondef.get("embed_scope", None),
					actiondef.get("escape_captures", None),
				)
			else:
				embed = None
			metascope = None
			if dbg: dbg(f"MATCH rtctx: {rtctx.name} pos: {pos} pattern: {patt.pattern} span: {match.span()} maingroup: {match.group()} groups: {[match.group(n) for n in range(patt.number_of_captures())]} actiondef: {actiondef}")
			mbegin, pos = match.span()
			if push:
				pushctx = self.get_context(rtctx.syntax, push)
				if pushctx:
					metascope = ctx_findprop(pushctx, "meta_scope", None)
					if metascope:
						self.push_scope(metascope)
			if mbegin < pos:
				if scope:
					self.push_scope(scope)
				if captures:
					for capidx, gscope in captures.items():
						gmbegin, gmend = match.span(capidx)
						if mbegin < gmbegin:
							self.write_token(text[mbegin:gmbegin])
							mbegin = gmbegin
						if gmbegin < gmend:
							self.push_scope(gscope)
							self.write_token(match.group(capidx))
							self.pop_scope()
							mbegin = gmend
					if mbegin < pos:
						self.write_token(text[mbegin:pos])
				else:
					self.write_token(match.group())
				if scope:
					self.pop_scope()
			if pop:
				pop = 1 if pop is True else pop
				handle_branching = not push
				i = 0
				while i < pop:
					newctx = self.contextstack[-1]
					i += 1 if not newctx.included or newctx.branch_meta else 0
					self.pop_context(handle_branching=handle_branching)
				if not push and not branch and not fail:
					newctx = self.contextstack[-1]
					while newctx.included and not newctx.branch_meta:
						self.pop_context(handle_branching=handle_branching)
						newctx = self.contextstack[-1]
					if not push and not newctx.included and not newctx.branch_meta:
						self.reset_context(newctx)
			if push:
				if embed and embed.content_scope:
					self.push_scope(embed.content_scope)
				self.push_context(push, do_metascope=not metascope, with_prototype=with_prototype, embed=embed)
			elif branch:
				branch_ctx = self.contextstack[-1]
				branch_point = actiondef.get("branch_point", None)
				branch_ctx.branch_meta = BranchMetadata(
					len(self.contextstack), # id of _pushed_ context will be +1
					branch_point,
					iter(branch),
					text,
					pos,
					self.io
				)
				self.io = StringIO()
				next_branch_name = next(branch_ctx.branch_meta.branches_iter)
				if dbg: dbg(f"BRANCH init from: {branch_point} @ {branch_ctx.name} (pos: {pos} text: {repr(text[pos:pos+8])}...) to: {next_branch_name}")
				self.push_context(next_branch_name, with_prototype=with_prototype)
			elif fail:
				try:
					rollback_ctx = next(filter(lambda x:x.branch_meta and x.branch_meta.branch_point == fail, reversed(self.contextstack)))
					pops = len(self.contextstack) - rollback_ctx.branch_meta.ctx_id
					if dbg: dbg(f"BRANCH failed at: {rtctx.name} (pos: {pos}) revert point: {fail} @ {rollback_ctx.name} pops: {pops}")
					for ipop in range(pops):
						self.pop_context(handle_branching=False)
					pos, text, prev_io = rollback_ctx.branch_meta.rollback()
					self.io.close()
					self.io = StringIO()
					try:
						next_branch_name = next(rollback_ctx.branch_meta.branches_iter)
						if dbg: dbg(f"BRANCH next from: {fail} @ {rollback_ctx.name} to: {next_branch_name}")
						self.push_context(next_branch_name, with_prototype=with_prototype)
					except StopIteration:
						self.io.close()
						self.io = prev_io
						rollback_ctx.branch_meta = None
				except StopIteration:
					if dbg: dbg(f"BRANCH failed at: {rtctx.name} revert point: {fail} not found")
					# doc says when this happens it's a nop
			elif not pop:
				newctx = self.contextstack[-1]
				while newctx.included and not newctx.branch_meta:
					self.pop_context()
					newctx = self.contextstack[-1]
				# if match.span()[1] <= match.span()[0] and rtctx is newctx:
				# 	raise NotImplementedError(f"match didn't advance ptr, and no context has been pushed or poped. This means that there's a missing feature implementation: {actiondef}")
				if not newctx.included and not newctx.branch_meta:
					self.reset_context(newctx)
		return pos, text

	def match_embed_and_rollback(self, rtctx, text, pos):
		match = rtctx.embed.escape_pattern.match(text, pos)
		if match:
			pops = len(self.contextstack) - rtctx.embed.rollback_id
			if dbg: dbg(f"EMBED: match: {match} pos: {pos} text: {repr(text[pos:pos+8])}... rollback pops: {pops}")
			mbegin, pos = match.span()
			if rtctx.embed.content_scope:
				self.pop_scope()
			if rtctx.embed.captures:
				for capidx, gscope in rtctx.embed.captures.items():
					gmbegin, gmend = match.span(capidx)
					if mbegin < gmbegin:
						self.write_token(text[mbegin:gmbegin])
						mbegin = gmbegin
					if gmbegin < gmend:
						self.push_scope(gscope)
						self.write_token(match.group(capidx))
						self.pop_scope()
						mbegin = gmend
				if mbegin < pos:
					self.write_token(text[mbegin:pos])
			else:
				self.write_token(match.group())
			for ipop in range(pops):
				self.pop_context(handle_branching=False)
			if dbg: dbg(f"EMBED: rollback to: {self.context}")
			return True, text, pos
		return False, text, pos


if __name__ == "__main__":
	# Maintain backwards compatibility while using modern components
	try:
		from app import SyntaxHighlighterApp
		app = SyntaxHighlighterApp()
		app.run()
	except ImportError:
		# Fallback to original implementation if new modules aren't available
		parser = argparse.ArgumentParser()
		parser.add_argument("-s", "--syntax", type=str, help="sublime-syntax to use", nargs="?", default=None)
		parser.add_argument("-c", "--color-scheme", type=str, help="sublime-color-scheme to use", nargs="?", default="Default")
		parser.add_argument("-d", "--debug", action="store_true", help="turn debugging on", default=False)
		parser.add_argument("-S", "--show-scopes", action="store_true", help="output scopes tags", default=False)
		parser.add_argument("-ls", "--list-syntaxes", action="store_true", help="list available syntaxes", default=False)
		parser.add_argument("-lc", "--list-color-schemes", action="store_true", help="list available color schemes", default=False)
		parser.add_argument("input_file", type=str, help="input file", nargs="?", default=None)
		args = parser.parse_args()
		global dbg
		if args.debug:
			dbg = print
			if dbg: dbg("="*20)
		else:
			dbg = None
		if args.list_syntaxes:
			import json
			print(
				json.dumps(
					{
						"syntaxes": all_syntaxes_names
					},
					indent=2
				)
			)
		if args.list_color_schemes:
			import json
			print(
				json.dumps(
				{
						"color-schemes": all_color_schemes_names
					},
					indent=2
				)
			)
		if args.list_syntaxes or args.list_color_schemes:
			exit()
		first_stdin_line = None
		input_stream = open(args.input_file, "r") if args.input_file else sys.stdin
		if args.syntax is None:
			fastloadpatts = (re.compile("^file_extensions:"), re.compile("^first_line_match"))
			all_syntaxes = loadsyntaxesmp(all_syntaxes_paths, lambda path:loadsyntax_until(path, fastloadpatts, cache=False))
			if args.input_file:
				file_ext = os.path.splitext(args.input_file)[1].lstrip(".")
				for syntax_name, syntax in all_syntaxes.items():
					if syntax:
						file_extensions = syntax.get("file_extensions", [])
						if file_ext in file_extensions:
							args.syntax = syntax_name
							break
			if args.syntax is None:
				for line in input_stream:
					first_stdin_line = line
					for syntax_name, syntax in all_syntaxes.items():
						if syntax:
							first_line_match = syntax.get("first_line_match", None)
							if first_line_match:
								if re.match(first_line_match, line):
									args.syntax = syntax_name
									break
					break
			del all_syntaxes
		if args.syntax is None:
			args.syntax = "Default"
		main_syntax_path = os.path.abspath(
			os.path.join(
				syntax_dir_path,
				f"{args.syntax}.{sublsynt_ext}"
			)
		)
		main_syntax = parsesyntax(
			loadsyntax(main_syntax_path)
		)
		color_scheme_path = os.path.abspath(
			os.path.join(
				color_scheme_dir_path,
				f"{args.color_scheme}.{sublcolscheme_ext}"
			)
		)
		color_scheme = parsecolorscheme(
			loadcolorscheme(color_scheme_path)
		)
		output = sys.stdout if not args.debug else StringIO()
		shl = SyntaxHighlighter(
			main_syntax,
			color_scheme,
			output,
			show_scopes=args.show_scopes
		)
		shl.begin()
		if first_stdin_line:
			shl.process(first_stdin_line)
			output.flush()
		for line in input_stream:
			shl.process(line)
			output.flush()
		shl.end()
		if args.debug:
			print(output.getvalue())
			output.close()
