"""
Modern syntax highlighter implementation using SOLID principles.
"""

import regex as re
from io import StringIO
from typing import Dict, Any, Optional, TextIO

from config import DebugConfig
from managers import (
    ScopeManager, ContextManager, RuntimeContext,
    BranchMetadata, WithPrototype, Embed
)
from output_writer import OutputWriter
from pattern_compiler import PatternCompiler
from loaders import SyntaxLoader
from sublsyntax import ctx_findprop


class ModernSyntaxHighlighter:
    """Modern syntax highlighter with separated concerns."""
    
    def __init__(
        self,
        syntax: Dict[str, Any],
        color_scheme: Dict[str, Any],
        output: TextIO,
        debug_config: DebugConfig,
        show_scopes: bool = False,
        syntax_loader: Optional[SyntaxLoader] = None
    ):
        self.main_syntax = syntax
        self.debug_config = debug_config
        
        # Initialize managers
        self.scope_manager = ScopeManager(debug_config, show_scopes)
        self.context_manager = ContextManager(debug_config)
        self.output_writer = OutputWriter(color_scheme, output, debug_config)
        self.pattern_compiler = PatternCompiler()
        self.syntax_loader = syntax_loader or SyntaxLoader()
        
        # Initialize with main syntax
        self.syntax_loader._cache_scope_mapping(syntax)
        
        # Pattern for push references
        self.re_pushref = re.compile(r"scope:([^#]+)(?:#(.+))?")
    
    def begin(self) -> None:
        """Initialize highlighting session."""
        assert len(self.context_manager.contextstack) == 0
        self._push_context("main")
        
        rtctx = self.context_manager.current_context
        scope = rtctx.syntax.get("scope", None)
        rtctx.metascope = scope
        if scope:
            self.scope_manager.push_scope(scope, self.output_writer)
    
    def process(self, text: str, pos: int = 0) -> str:
        """
        Process text for syntax highlighting.
        
        Args:
            text: Text to process
            pos: Starting position
            
        Returns:
            Processed text
        """
        self.debug_config.debug(f"init ANALYZE pos: {pos} text: {repr(text[pos:pos + 8])}...")
        
        # Update branch metadata
        for ctx in self.context_manager.contextstack:
            if ctx.branch_meta:
                ctx.branch_meta.prev_text.write(text)
        
        while pos < len(text):
            rtctx = self.context_manager.current_context
            rtctx_curr_action_id = rtctx.curr_action_id
            
            # Handle embed escape patterns
            if rtctx_curr_action_id == 0 and rtctx.embed:
                didRollback, text, pos = self._match_embed_and_rollback(rtctx, text, pos)
                if didRollback:
                    continue
            
            # Check if we've exhausted actions in current context
            if rtctx_curr_action_id >= rtctx.lenactionlist:
                if rtctx.included:
                    self._pop_context()
                    continue
                
                self.output_writer.write_raw(text[pos])
                pos += 1
                self.context_manager.reset_context(rtctx)
                
                if self.debug_config.enabled and pos < len(text):
                    self.debug_config.debug(f"loop ANALYZE pos: {pos} text: {repr(text[pos:pos + 8])}...")
                continue
            
            # Process current action
            actiondef = rtctx.actionlist[rtctx_curr_action_id]
            rtctx.curr_action_id = rtctx_curr_action_id + 1
            opos = pos
            
            action = next(iter(actiondef))
            if action == "match":
                pos, text = self._action_match(rtctx, text, pos, actiondef)
            elif action == "include":
                self._push_context(actiondef["include"], included=True)
            
            if self.debug_config.enabled and opos != pos:
                self.debug_config.debug(f"step ANALYZE pos: {pos} text: {repr(text[pos:pos + 8])}...")
        
        return text
    
    def end(self) -> None:
        """Finalize highlighting session."""
        while self.context_manager.contextstack:
            self._pop_context()
    
    def _push_context(
        self,
        key,
        included: bool = False,
        syntax: Optional[Dict[str, Any]] = None,
        do_metascope: bool = True,
        with_prototype: Optional[WithPrototype] = None,
        embed: Optional[Embed] = None
    ) -> None:
        """Push a new context onto the stack."""
        if syntax is None:
            syntax = self.context_manager.current_syntax or self.main_syntax
        
        # Handle list of contexts
        if isinstance(key, list) and not any(map(lambda x: isinstance(x, dict), key)):
            for k in key:
                self._push_context(
                    k,
                    included=included,
                    syntax=syntax,
                    do_metascope=do_metascope,
                    with_prototype=with_prototype
                )
            return
        
        # Handle external syntax references
        if isinstance(key, str):
            key, syntax = self._resolve_external_syntax(key, syntax)
        
        ctx = self.context_manager.get_context(syntax, key)
        if ctx is not None:
            self._create_and_push_runtime_context(
                syntax, key, ctx, included, with_prototype, embed, do_metascope
            )
        elif key != "prototype":
            raise KeyError(f"push_context: context: {key} not found; ctx: {self.context_manager.current_context}")
    
    def _resolve_external_syntax(self, key: str, syntax: Dict[str, Any]) -> tuple:
        """Resolve external syntax references."""
        if key.startswith("scope:"):
            pushref = self.re_pushref.match(key)
            if not pushref:
                raise ValueError(f"push_context: push reference has an invalid format, expecting scope:.+(#.+)? got: {key}")
            
            extscope, context_key = pushref.groups()
            if not context_key:
                context_key = "main"
            
            syntax = self.syntax_loader.load_syntax_by_scope(extscope)
            if not syntax:
                raise KeyError(f"push_context: external syntax (by scope): {extscope} not found, are you missing a syntax file?")
            
            return context_key, syntax
        
        elif key.startswith("packages/"):  # hacky
            from sublsyntax import syntax_dir_path
            import os
            
            mapped_path = os.path.join(syntax_dir_path, os.path.basename(key))
            syntax = self.syntax_loader.load_syntax_by_path(mapped_path)
            if not syntax:
                raise KeyError(f"push_context: external syntax: '{mapped_path}' not found, are you missing a syntax file?")
            
            return "main", syntax
        
        return key, syntax
    
    def _create_and_push_runtime_context(
        self,
        syntax: Dict[str, Any],
        key,
        ctx: list,
        included: bool,
        with_prototype: Optional[WithPrototype],
        embed: Optional[Embed],
        do_metascope: bool
    ) -> None:
        """Create and push a new runtime context."""
        if with_prototype is None:
            with_prototype = self.context_manager.current_context.with_prototype if self.context_manager.current_context else None
        
        if embed is None:
            embed = self.context_manager.current_context.embed if self.context_manager.current_context else None
        
        rtctx = RuntimeContext(syntax, key, ctx, included, with_prototype, embed)
        
        if not included:
            self._handle_scope_clearing(ctx)
            self._handle_metascopes(ctx, rtctx, do_metascope)
        
        self.context_manager.push_context(rtctx)
        
        if not included and key != "prototype":
            self._reset_context(rtctx)
    
    def _handle_scope_clearing(self, ctx: list) -> None:
        """Handle scope clearing directives."""
        clear_scopes = ctx_findprop(ctx, "clear_scopes", None)
        if clear_scopes:
            ctxstack_len = len(self.context_manager.contextstack)
            n = ctxstack_len if clear_scopes is True else clear_scopes
            self.debug_config.debug(f"clear_scopes: n: {n}")
            
            i = ctxstack_len - 1
            while i >= 0 and n > 0:
                clrctx = self.context_manager.contextstack[i]
                if not clrctx.included:
                    self.debug_config.debug(f"clear_scopes: clearing: {clrctx.name} i: {i}")
                    if clrctx.meta_content_scope:
                        self.scope_manager.pop_scope(self.output_writer)
                        clrctx.meta_content_scope = None
                    if clrctx.metascope:
                        self.scope_manager.pop_scope(self.output_writer)
                        clrctx.metascope = None
                    n -= 1
                i -= 1
    
    def _handle_metascopes(self, ctx: list, rtctx: RuntimeContext, do_metascope: bool) -> None:
        """Handle metascope and meta_content_scope."""
        metascope = ctx_findprop(ctx, "meta_scope", None)
        if metascope:
            rtctx.metascope = metascope
            if do_metascope:
                self.scope_manager.push_scope(metascope, self.output_writer)
        
        meta_content_scope = ctx_findprop(ctx, "meta_content_scope", None)
        if meta_content_scope:
            rtctx.meta_content_scope = meta_content_scope
            self.scope_manager.push_scope(meta_content_scope, self.output_writer)
    
    def _pop_context(self, handle_branching: bool = True) -> RuntimeContext:
        """Pop context and handle cleanup."""
        rtctx = self.context_manager.pop_context(handle_branching)
        
        # Handle scope cleanup
        if not rtctx.included:
            if rtctx.meta_content_scope:
                self.scope_manager.pop_scope(self.output_writer)
                rtctx.meta_content_scope = None
            if rtctx.metascope:
                self.scope_manager.pop_scope(self.output_writer)
                rtctx.metascope = None
        
        # Handle branching
        if handle_branching and self.context_manager.contextstack:
            nextctx = self.context_manager.contextstack[-1]
            if nextctx.branch_meta:
                self.debug_config.debug(f"BRANCH success: branch: {rtctx.name} of {nextctx.branch_meta.branch_point} @ {nextctx.name}")
                prev_io = nextctx.branch_meta.prev_io
                prev_io.write(self.output_writer.getvalue())
                self.output_writer.close()
                self.output_writer.output = prev_io
                nextctx.branch_meta = None
        
        return rtctx
    
    def _reset_context(self, rtctx: RuntimeContext) -> None:
        """Reset context and handle prototypes."""
        self.context_manager.reset_context(rtctx)
        
        if rtctx.name != "prototype":
            if rtctx.with_prototype:
                assert rtctx.with_prototype.context
                self._push_context(
                    rtctx.with_prototype.context,
                    included=True,
                    syntax=rtctx.with_prototype.syntax
                )
            
            if not any(map(lambda x: not x.get("meta_include_prototype", True), rtctx.actionlist)):
                self._push_context("prototype", included=True)
    
    def _action_match(self, rtctx: RuntimeContext, text: str, pos: int, actiondef: dict) -> tuple:
        """Handle match action - this is still complex and could be split further."""
        # This method is still quite large - it could be split into smaller methods
        # but for now, let's keep the core logic together while extracting helpers
        
        patt = actiondef["match"]
        if isinstance(patt, str):
            pattern = patt
            patt = self.pattern_compiler.compile_pattern(patt, rtctx)
            patt.pattern = pattern
            actiondef["match"] = patt
        
        match = patt.match(text, pos)
        if not match:
            return pos, text
        
        # Extract action parameters
        action_params = self._extract_action_parameters(actiondef, rtctx, match)
        
        # Log match
        self.debug_config.debug(
            f"MATCH rtctx: {rtctx.name} pos: {pos} pattern: {patt.pattern} "
            f"span: {match.span()} maingroup: {match.group()} "
            f"groups: {[match.group(n) for n in range(patt.number_of_captures())]} "
            f"actiondef: {actiondef}"
        )
        
        mbegin, pos = match.span()
        
        # Handle the match based on action type
        return self._process_match_action(
            rtctx, text, pos, mbegin, match, action_params
        )
    
    def _extract_action_parameters(self, actiondef: dict, rtctx: RuntimeContext, match) -> dict:
        """Extract and process action parameters."""
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
            embed = self._process_embed_action(actiondef, rtctx, match, push)
            push = embed
        
        return {
            'scope': scope,
            'captures': captures,
            'push': push,
            'pop': pop,
            'branch': branch,
            'fail': fail,
            'embed': embed,
            'with_prototype': with_prototype
        }
    
    def _process_embed_action(self, actiondef: dict, rtctx: RuntimeContext, match, push) -> Embed:
        """Process embed action parameters."""
        try:
            embed_escape = actiondef["escape"]
        except KeyError:
            raise KeyError(f"embed_escape is required when specifying an embed. ctx: {rtctx}")
        
        # Substitute capture groups in escape pattern
        try:
            gi = 0
            while True:
                if match.group(gi):
                    embed_escape = re.sub(f"(?<=\\b)\\\\{gi}(?=\\b)", match.group(gi), embed_escape)
                gi += 1
        except IndexError:
            pass
        
        if isinstance(embed_escape, str):
            embed_escape = self.pattern_compiler.compile_pattern(embed_escape, rtctx)
            actiondef["escape"] = embed_escape
        
        # Find rollback point
        try:
            revid, itm = next(filter(lambda x: not x[1].included, enumerate(reversed(self.context_manager.contextstack))))
            rollback_id = len(self.context_manager.contextstack) - revid - 1
        except StopIteration:
            rollback_id = len(self.context_manager.contextstack) - 1
        
        return Embed(
            embed_escape,
            rollback_id,
            actiondef.get("embed_scope", None),
            actiondef.get("escape_captures", None),
        )
    
    def _process_match_action(self, rtctx: RuntimeContext, text: str, pos: int, mbegin: int, match, params: dict) -> tuple:
        """Process the actual match action."""
        # Handle push metascope
        metascope = None
        if params['push']:
            pushctx = self.context_manager.get_context(rtctx.syntax, params['push'])
            if pushctx:
                metascope = ctx_findprop(pushctx, "meta_scope", None)
                if metascope:
                    self.scope_manager.push_scope(metascope, self.output_writer)
        
        # Write matched text with scopes
        if mbegin < pos:
            self._write_matched_text(text, mbegin, pos, match, params)
        
        # Handle pop operations
        if params['pop']:
            self._handle_pop_operation(params)
        
        # Handle push/branch/fail operations
        self._handle_context_operations(params, rtctx, text, pos)
        
        return pos, text
    
    def _write_matched_text(self, text: str, mbegin: int, pos: int, match, params: dict) -> None:
        """Write matched text with appropriate scoping."""
        if params['scope']:
            self.scope_manager.push_scope(params['scope'], self.output_writer)
        
        if params['captures']:
            self._write_with_captures(text, mbegin, pos, match, params['captures'])
        else:
            self.output_writer.write_token(match.group(), self.scope_manager.scopestack)
        
        if params['scope']:
            self.scope_manager.pop_scope(self.output_writer)
    
    def _write_with_captures(self, text: str, mbegin: int, pos: int, match, captures: dict) -> None:
        """Write text with capture group scoping."""
        current_pos = mbegin
        
        for capidx, gscope in captures.items():
            gmbegin, gmend = match.span(capidx)
            
            # Write text before capture group
            if current_pos < gmbegin:
                self.output_writer.write_token(text[current_pos:gmbegin], self.scope_manager.scopestack)
                current_pos = gmbegin
            
            # Write capture group with scope
            if gmbegin < gmend:
                self.scope_manager.push_scope(gscope, self.output_writer)
                self.output_writer.write_token(match.group(capidx), self.scope_manager.scopestack)
                self.scope_manager.pop_scope(self.output_writer)
                current_pos = gmend
        
        # Write remaining text
        if current_pos < pos:
            self.output_writer.write_token(text[current_pos:pos], self.scope_manager.scopestack)
    
    def _handle_pop_operation(self, params: dict) -> None:
        """Handle context pop operations."""
        pop = 1 if params['pop'] is True else params['pop']
        handle_branching = not params['push']
        
        i = 0
        while i < pop:
            newctx = self.context_manager.contextstack[-1]
            i += 1 if not newctx.included or newctx.branch_meta else 0
            self._pop_context(handle_branching=handle_branching)
        
        if not params['push'] and not params['branch'] and not params['fail']:
            newctx = self.context_manager.contextstack[-1]
            while newctx.included and not newctx.branch_meta:
                self._pop_context(handle_branching=handle_branching)
                newctx = self.context_manager.contextstack[-1]
            
            if not params['push'] and not newctx.included and not newctx.branch_meta:
                self._reset_context(newctx)
    
    def _handle_context_operations(self, params: dict, rtctx: RuntimeContext, text: str, pos: int) -> None:
        """Handle push, branch, and fail operations."""
        if params['push']:
            if params['embed'] and params['embed'].content_scope:
                self.scope_manager.push_scope(params['embed'].content_scope, self.output_writer)
            
            self._push_context(
                params['push'],
                do_metascope=False,  # Already handled metascope
                with_prototype=params['with_prototype'],
                embed=params['embed']
            )
        
        elif params['branch']:
            self._handle_branch_operation(params, text, pos)
        
        elif params['fail']:
            self._handle_fail_operation(params, rtctx, text, pos)
        
        elif not params['pop']:
            # Default behavior when no explicit action
            newctx = self.context_manager.contextstack[-1]
            while newctx.included and not newctx.branch_meta:
                self._pop_context()
                newctx = self.context_manager.contextstack[-1]
            
            if not newctx.included and not newctx.branch_meta:
                self._reset_context(newctx)
    
    def _handle_branch_operation(self, params: dict, text: str, pos: int) -> None:
        """Handle branch operations."""
        branch_ctx = self.context_manager.contextstack[-1]
        branch_point = params.get('branch_point')
        
        branch_ctx.branch_meta = BranchMetadata(
            len(self.context_manager.contextstack),
            branch_point,
            iter(params['branch']),
            text,
            pos,
            self.output_writer.output
        )
        
        self.output_writer.output = StringIO()
        next_branch_name = next(branch_ctx.branch_meta.branches_iter)
        
        self.debug_config.debug(
            f"BRANCH init from: {branch_point} @ {branch_ctx.name} "
            f"(pos: {pos} text: {repr(text[pos:pos+8])}...) to: {next_branch_name}"
        )
        
        self._push_context(next_branch_name, with_prototype=params['with_prototype'])
    
    def _handle_fail_operation(self, params: dict, rtctx: RuntimeContext, text: str, pos: int) -> None:
        """Handle fail operations."""
        try:
            rollback_ctx = next(filter(
                lambda x: x.branch_meta and x.branch_meta.branch_point == params['fail'],
                reversed(self.context_manager.contextstack)
            ))
            
            pops = len(self.context_manager.contextstack) - rollback_ctx.branch_meta.ctx_id
            self.debug_config.debug(
                f"BRANCH failed at: {rtctx.name} (pos: {pos}) "
                f"revert point: {params['fail']} @ {rollback_ctx.name} pops: {pops}"
            )
            
            for ipop in range(pops):
                self._pop_context(handle_branching=False)
            
            pos, text, prev_io = rollback_ctx.branch_meta.rollback()
            self.output_writer.close()
            self.output_writer.output = StringIO()
            
            try:
                next_branch_name = next(rollback_ctx.branch_meta.branches_iter)
                self.debug_config.debug(
                    f"BRANCH next from: {params['fail']} @ {rollback_ctx.name} to: {next_branch_name}"
                )
                self._push_context(next_branch_name, with_prototype=params['with_prototype'])
            except StopIteration:
                self.output_writer.close()
                self.output_writer.output = prev_io
                rollback_ctx.branch_meta = None
        
        except StopIteration:
            self.debug_config.debug(
                f"BRANCH failed at: {rtctx.name} revert point: {params['fail']} not found"
            )
            # doc says when this happens it's a nop
    
    def _match_embed_and_rollback(self, rtctx: RuntimeContext, text: str, pos: int) -> tuple:
        """Handle embed escape pattern matching."""
        match = rtctx.embed.escape_pattern.match(text, pos)
        if not match:
            return False, text, pos
        
        pops = len(self.context_manager.contextstack) - rtctx.embed.rollback_id
        self.debug_config.debug(
            f"EMBED: match: {match} pos: {pos} text: {repr(text[pos:pos+8])}... rollback pops: {pops}"
        )
        
        mbegin, pos = match.span()
        
        if rtctx.embed.content_scope:
            self.scope_manager.pop_scope(self.output_writer)
        
        if rtctx.embed.captures:
            self._write_with_captures(text, mbegin, pos, match, rtctx.embed.captures)
        else:
            self.output_writer.write_token(match.group(), self.scope_manager.scopestack)
        
        for ipop in range(pops):
            self._pop_context(handle_branching=False)
        
        self.debug_config.debug(f"EMBED: rollback to: {self.context_manager.current_context}")
        return True, text, pos