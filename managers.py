"""
Scope and context management for syntax highlighting.
"""

from typing import List, Dict, Any, Optional, TextIO
from io import StringIO

from config import DebugConfig


class ScopeManager:
    """Manages scope stack for syntax highlighting."""
    
    def __init__(self, debug_config: DebugConfig, show_scopes: bool = False):
        self.scopestack: List[List[str]] = []
        self.scopepops: List[int] = []
        self.debug_config = debug_config
        self.show_scopes = show_scopes
    
    def push_scope(self, scopes: str, output_writer) -> None:
        """
        Push new scopes onto the stack.
        
        Args:
            scopes: Space-separated scope names
            output_writer: Writer for formatted output
        """
        scopes_list = scopes.split(" ")
        self.scopepops.append(len(scopes_list))
        
        for scope in scopes_list:
            self.scopestack.append(scope.split("."))
            token_color = output_writer.get_token_color(None, self.scopestack)
            self.debug_config.debug(f"push_scope: {scope} color: {token_color}")
            output_writer.set_color(*token_color)
            
            if self.show_scopes:
                output_writer.write_raw(f"<{scope}>")
    
    def pop_scope(self, output_writer) -> None:
        """
        Pop scopes from the stack.
        
        Args:
            output_writer: Writer for formatted output
        """
        if not self.scopepops:
            self.debug_config.debug("Warning: Attempting to pop scope when scopepops is empty")
            return
            
        npops = self.scopepops.pop()
        for i in range(npops):
            if not self.scopestack:
                self.debug_config.debug("Warning: Attempting to pop from empty scopestack")
                break
                
            rtscope = self.scopestack.pop()
            if self.show_scopes:
                output_writer.write_raw(f"</{'.'.join(rtscope)}>")
            
            token_color = output_writer.get_token_color(None, self.scopestack)
            self.debug_config.debug(f"pop_scope: {rtscope} color: {token_color}")
            output_writer.set_color(*token_color)


class BranchMetadata:
    """Metadata for branch context management."""
    
    def __init__(self, ctx_id: int, branch_point: str, branches_iter, prev_text: str, prev_pos: int, prev_io: TextIO):
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
    """Represents a with_prototype context."""
    
    def __init__(self, context, syntax):
        self.context = context
        self.syntax = syntax


class Embed:
    """Represents an embed context."""
    
    def __init__(self, escape_pattern, rollback_id: int, content_scope: Optional[str], captures: Optional[Dict]):
        self.escape_pattern = escape_pattern
        self.rollback_id = rollback_id
        self.content_scope = content_scope
        self.captures = captures


class RuntimeContext:
    """Runtime context for syntax highlighting."""
    
    def __init__(self, syntax: Dict[str, Any], key, actionlist: List[Dict], included: bool, with_prototype, embed):
        self.syntax = syntax
        self.name = key if isinstance(key, str) else str(key)
        self.actionlist = actionlist
        self.lenactionlist = len(actionlist)
        self.curr_action_id = 0
        self.included = included
        self.metascope: Optional[str] = None
        self.meta_content_scope: Optional[str] = None
        self.branch_meta: Optional[BranchMetadata] = None
        self.with_prototype = with_prototype
        self.embed = embed
    
    def __str__(self):
        return f"{self.name} included: {self.included} metascope: {self.metascope} meta_content_scope: {self.meta_content_scope} branch_meta: {'yes' if self.branch_meta else 'no'} syntax: {self.syntax['name']}"


class ContextManager:
    """Manages context stack for syntax highlighting."""
    
    def __init__(self, debug_config: DebugConfig):
        self.contextstack: List[RuntimeContext] = []
        self.debug_config = debug_config
    
    @property
    def current_context(self) -> Optional[RuntimeContext]:
        """Get the current context."""
        return self.contextstack[-1] if self.contextstack else None
    
    @property
    def current_syntax(self) -> Optional[Dict[str, Any]]:
        """Get the current context's syntax."""
        return self.contextstack[-1].syntax if self.contextstack else None
    
    def push_context(self, rtctx: RuntimeContext) -> None:
        """Push a new runtime context onto the stack."""
        self.contextstack.append(rtctx)
        self.debug_config.debug(
            "push:" + " <- ".join(
                map(lambda x: f"{x.name}{'(inc)' if x.included else ''}{'(branch)' if x.branch_meta else ''}{'(embed)' if x.embed else ''}({x.syntax['name']})", 
                    reversed(self.contextstack))
            )
        )
    
    def pop_context(self, handle_branching: bool = True) -> RuntimeContext:
        """Pop the current context from the stack."""
        self.debug_config.debug(
            "pop:" + " <- ".join(
                map(lambda x: f"{x.name}{'(inc)' if x.included else ''}{'(branch)' if x.branch_meta else ''}{'(embed)' if x.embed else ''}({x.syntax['name']})", 
                    reversed(self.contextstack))
            )
        )
        
        rtctx = self.contextstack.pop()
        
        if handle_branching and self.contextstack:
            nextctx = self.contextstack[-1]
            if nextctx.branch_meta:
                self.debug_config.debug(f"BRANCH success: branch: {rtctx.name} of {nextctx.branch_meta.branch_point} @ {nextctx.name}")
                # Branch handling logic will be moved to the appropriate manager
        
        assert rtctx.branch_meta is None
        return rtctx
    
    def reset_context(self, rtctx: RuntimeContext) -> None:
        """Reset context to beginning of action list."""
        if rtctx.included:
            raise Exception(f"cannot reset_context: {rtctx}")
        
        rtctx.curr_action_id = 0
        self.debug_config.debug(f"reset_context: {rtctx}")
    
    def get_context(self, syntax: Dict[str, Any], key) -> Optional[List[Dict]]:
        """Get context definition from syntax."""
        if isinstance(key, str):
            return syntax["contexts"].get(key, None)
        return key  # anonymous context