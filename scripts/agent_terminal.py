"""Keep large shell input out of macOS PTY line buffers."""
from pathlib import Path
import shlex
import tempfile

from openhands.sdk.tool import register_tool
from openhands.tools.terminal import TerminalTool, TerminalExecutor


class ScriptTerminalExecutor(TerminalExecutor):
    def __init__(self, **kwargs):
        self.scripts = tempfile.TemporaryDirectory(prefix='workbench-terminal-')
        self.sequence = 0
        super().__init__(**kwargs)

    def __call__(self, action, conversation=None):
        if not action.is_input and ('\n' in action.command or len(action.command.encode()) > 512):
            self.sequence += 1
            path = Path(self.scripts.name) / f'{self.sequence}.sh'
            path.write_text(action.command, encoding='utf-8')
            path.chmod(0o600)
            # Source preserves this terminal's cwd/environment and final exit status.
            # Keep scripts until close so background/soft-timeout commands can finish.
            staged = action.model_copy(update={'command': 'source ' + shlex.quote(str(path))})
            result = super().__call__(staged, conversation)
            return result.model_copy(update={'command': action.command})
        return super().__call__(action, conversation)

    def close(self):
        try:
            super().close()
        finally:
            self.scripts.cleanup()


class WorkbenchTerminalTool(TerminalTool):
    @classmethod
    def create(cls, conv_state):
        executor = ScriptTerminalExecutor(
            working_dir=conv_state.workspace.working_dir,
            terminal_type='subprocess',
            full_output_save_dir=conv_state.env_observation_persistence_dir,
        )
        return TerminalTool.create(conv_state, executor=executor)


register_tool(WorkbenchTerminalTool.name, WorkbenchTerminalTool)
