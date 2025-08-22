import os
import yaml
from itertools import chain


file_ext = "sublime-syntax"
syntax_dir_path = os.path.join(
	os.path.dirname(__file__) or ".",
	"syntax"
)
all_syntaxes_basenames = list(
	filter(
		lambda x:x.endswith(file_ext),
		os.listdir(syntax_dir_path)
	)
)
all_syntaxes_names = list(
	map(
		lambda x: os.path.splitext(x)[0],
		all_syntaxes_basenames
	)
)
all_syntaxes_paths = list(
	map(
		lambda x: os.path.abspath(
			os.path.join(
				syntax_dir_path,
				x
			)
		),
		all_syntaxes_basenames
	)
)
# Module-level cache - can be improved to instance-based
LOAD_SYNTAX_CACHE = {}
__hl_parsed_key = "__hl_parsed"


def ctx_findprop(ctx, key, default):
	return (list(filter(lambda x:key in x, ctx)) or [{key:default}])[0].get(key, default)


def loadsyntax(path, cache=True):
	"""Load syntax from file with optional caching."""
	if cache and path in LOAD_SYNTAX_CACHE:
		return LOAD_SYNTAX_CACHE[path]
	with open(path, "rb") as f:
		syntax = yaml.load(f, Loader=yaml.SafeLoader)
		if cache:
			LOAD_SYNTAX_CACHE[path] = syntax
		return syntax


def clear_syntax_cache():
	"""Clear the global syntax cache - useful for testing."""
	global LOAD_SYNTAX_CACHE
	LOAD_SYNTAX_CACHE = {}


def loadsyntax_until(path, marker_regexes, cache=True):
	if cache and path in LOAD_SYNTAX_CACHE:
		return LOAD_SYNTAX_CACHE[path]
	with open(path, "r") as f:
		loaded_lines = []
		s = 0
		nmarkers = len(marker_regexes)
		for line in f:
			if s < nmarkers:
				if marker_regexes[s].match(line):
					s += 1
			elif line.strip().endswith(":"):
				syntax = yaml.load("".join(loaded_lines), Loader=yaml.SafeLoader)
				if cache:
					LOAD_SYNTAX_CACHE[path] = syntax
				return syntax
			loaded_lines.append(line)
	return None


def loadsyntaxesmp(paths, syntaxloader=loadsyntax):
	from multiprocessing.pool import ThreadPool as MPPool
	def threadloadsyntax(path):
		return os.path.splitext(os.path.basename(path))[0], syntaxloader(path)
	with MPPool() as p:
		return {k: v for k, v in p.map(threadloadsyntax, paths)}


def parsesyntax(syntax: dict, postlazyloadsyntax = lambda x: x):
	if __hl_parsed_key in syntax:
		return syntax
	def _syntax_merge_vars(*s):
		return {k: v for k, v in chain(*map(dict.items, map(lambda x:x.get("variables", None) or {}, s)))}
	def _syntax_merge_contexts(*s):
		result = {}
		for synt in s:
			ctx = synt["contexts"]
			for ctxname in ctx:
				if ctxname not in result:
					result[ctxname] = ctx[ctxname]
				elif ctx_findprop(ctx[ctxname], "meta_prepend", False):
					result[ctxname] = ctx[ctxname] + result[ctxname]
				elif ctx_findprop(ctx[ctxname], "meta_append", False):
					result[ctxname] = result[ctxname] + ctx[ctxname]
				else:
					result[ctxname] = ctx[ctxname] + result[ctxname]
		return result
	parent_syntaxes = syntax.get("extends", None)
	if parent_syntaxes:
		if isinstance(parent_syntaxes, str):
			parent_syntaxes = [parent_syntaxes]
		parent_syntaxes = list(
			map(
				lambda x: parsesyntax(
					loadsyntax(
						os.path.abspath(
							os.path.join(
								syntax_dir_path,
								os.path.basename(x)
							)
						)
					),
					postlazyloadsyntax=postlazyloadsyntax
				),
				parent_syntaxes
			)
		)
		syntax["variables"] = _syntax_merge_vars(*parent_syntaxes, syntax)
		syntax["contexts"] = _syntax_merge_contexts(*parent_syntaxes, syntax)
	syntax[__hl_parsed_key] = True
	postlazyloadsyntax(syntax)
	return syntax

	