import ast
import asyncio
import aiohttp
import inspect
import io
import textwrap
import traceback
import types
import re
import contextlib
from contextlib import redirect_stdout
from copy import copy

from typing import Iterable, List

import discord
from discord.ext import commands

from .utils.chat_formatting import box, pagify

"""
Notice:

95% of the below code came from R.Danny which can be found here:

https://github.com/Rapptz/RoboDanny/blob/master/cogs/repl.py
"""

_ = lambda x: x

START_CODE_BLOCK_RE = re.compile(r"^((```py)(?=\s)|(```))")


class Dev(commands.Cog):
    """Various development focused utilities."""

    def __init__(self):
        super().__init__()
        self._last_result = None
        self.sessions = set()

    @staticmethod
    async def send_interactive(
        ctx: commands.Context, messages: Iterable[str], box_lang: str = None, timeout: int = 15
    ) -> List[discord.Message]:
        """Send multiple messages interactively.
        The user will be prompted for whether or not they would like to view
        the next message, one at a time. They will also be notified of how
        many messages are remaining on each prompt.
        Parameters
        ----------
        messages : `iterable` of `str`
            The messages to send.
        box_lang : str
            If specified, each message will be contained within a codeblock of
            this language.
        timeout : int
            How long the user has to respond to the prompt before it times out.
            After timing out, the bot deletes its prompt message.
        """
        messages = tuple(messages)
        ret = []

        for idx, page in enumerate(messages, 1):
            if box_lang is None:
                msg = await ctx.send(page)
            else:
                msg = await ctx.send(box(page, lang=box_lang))
            ret.append(msg)
            n_remaining = len(messages) - idx
            if n_remaining > 0:
                if n_remaining == 1:
                    plural = ""
                    is_are = "is"
                else:
                    plural = "s"
                    is_are = "are"
                query = await ctx.send(
                    "There {} still {} message{} remaining. "
                    "Type `more` to continue."
                    "".format(is_are, n_remaining, plural)
                )
                try:
                    def check_message(msg):
                        return ctx.channel == msg.channel and ctx.author == msg.author and msg.content.lower() == "more"
                    resp = await ctx.bot.wait_for(
                        "message",
                        check=check_message,
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    with contextlib.suppress(discord.HTTPException):
                        await query.delete()
                    break
                else:
                    try:
                        await ctx.channel.delete_messages((query, resp))
                    except (discord.HTTPException, AttributeError):
                        # In case the bot can't delete other users' messages,
                        # or is not a bot account
                        # or channel is a DM
                        with contextlib.suppress(discord.HTTPException):
                            await query.delete()
        return ret

    @staticmethod
    async def tick(ctx : commands.Context) -> bool:
        """Add a tick reaction to the command message.
        Returns
        -------
        bool
            :code:`True` if adding the reaction succeeded.
        """
        try:
            await ctx.message.add_reaction("✅")
        except discord.HTTPException:
            return False
        else:
            return True

    @staticmethod
    def async_compile(source, filename, mode):
        return compile(source, filename, mode, flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, optimize=0)

    @staticmethod
    async def maybe_await(coro):
        for i in range(2):
            if inspect.isawaitable(coro):
                coro = await coro
            else:
                return coro
        return coro

    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return START_CODE_BLOCK_RE.sub("", content)[:-3]

        # remove `foo`
        return content.strip("` \n")

    @staticmethod
    def get_syntax_error(e):
        """Format a syntax error to send to the user.

        Returns a string representation of the error formatted as a codeblock.
        """
        if e.text is None:
            return box("{0.__class__.__name__}: {0}".format(e), lang="py")
        return box(
            "{0.text}\n{1:>{0.offset}}\n{2}: {0}".format(e, "^", type(e).__name__), lang="py"
        )

    @staticmethod
    def get_pages(msg: str):
        """Pagify the given message for output to the user."""
        return pagify(msg, delims=["\n", " "], priority=True, shorten_by=10)

    @staticmethod
    def sanitize_output(ctx: commands.Context, input_: str) -> str:
        """Hides the bot's token from a string."""
        token = ctx.bot.http.token
        return re.sub(re.escape(token), "[EXPUNGED]", input_, re.I)

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx, *, code):
        """Evaluate a statement of python code.

        The bot will always respond with the return value of the code.
        If the return value of the code is a coroutine, it will be awaited,
        and the result of that will be the bot's response.

        Note: Only one statement may be evaluated. Using certain restricted
        keywords, e.g. yield, will result in a syntax error. For multiple
        lines or asynchronous code, see [p]repl or [p]eval.

        Environment Variables:
            ctx      - command invokation context
            bot      - bot object
            channel  - the current channel object
            author   - command author's member object
            message  - the command's message object
            discord  - discord.py library
            commands - redbot.core.commands
            _        - The result of the last dev command.
        """
        env = {
            "bot": ctx.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "asyncio": asyncio,
            "aiohttp": aiohttp,
            "discord": discord,
            "commands": commands,
            "_": self._last_result,
            "__name__": "__main__",
        }

        code = self.cleanup_code(code)

        try:
            compiled = self.async_compile(code, "<string>", "eval")
            result = await self.maybe_await(eval(compiled, env))
        except SyntaxError as e:
            await ctx.send(self.get_syntax_error(e))
            return
        except Exception as e:
            await ctx.send(box("{}: {!s}".format(type(e).__name__, e), lang="py"))
            return

        self._last_result = result
        result = self.sanitize_output(ctx, str(result))

        await self.send_interactive(ctx, self.get_pages(result), box_lang="py")

    @commands.command(name="eval")
    @commands.is_owner()
    async def _eval(self, ctx, *, body: str):
        """Execute asynchronous code.

        This command wraps code into the body of an async function and then
        calls and awaits it. The bot will respond with anything printed to
        stdout, as well as the return value of the function.

        The code can be within a codeblock, inline code or neither, as long
        as they are not mixed and they are formatted correctly.

        Environment Variables:
            ctx      - command invokation context
            bot      - bot object
            channel  - the current channel object
            author   - command author's member object
            message  - the command's message object
            discord  - discord.py library
            commands - redbot.core.commands
            _        - The result of the last dev command.
        """
        env = {
            "bot": ctx.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "asyncio": asyncio,
            "aiohttp": aiohttp,
            "discord": discord,
            "commands": commands,
            "_": self._last_result,
            "__name__": "__main__",
        }

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = "async def func():\n%s" % textwrap.indent(body, "  ")

        try:
            compiled = self.async_compile(to_compile, "<string>", "exec")
            exec(compiled, env)
        except SyntaxError as e:
            return await ctx.send(self.get_syntax_error(e))

        func = env["func"]
        result = None
        try:
            with redirect_stdout(stdout):
                result = await func()
        except:
            printed = "{}{}".format(stdout.getvalue(), traceback.format_exc())
        else:
            printed = stdout.getvalue()
            await self.tick(ctx)

        if result is not None:
            self._last_result = result
            msg = "{}{}".format(printed, result)
        else:
            msg = printed
        msg = self.sanitize_output(ctx, msg)

        await self.send_interactive(ctx, self.get_pages(msg), box_lang="py")

    @commands.command()
    @commands.is_owner()
    async def repl(self, ctx):
        """Open an interactive REPL.

        The REPL will only recognise code as messages which start with a
        backtick. This includes codeblocks, and as such multiple lines can be
        evaluated.
        """
        variables = {
            "ctx": ctx,
            "bot": ctx.bot,
            "message": ctx.message,
            "guild": ctx.guild,
            "channel": ctx.channel,
            "author": ctx.author,
            "asyncio": asyncio,
            "_": None,
            "__builtins__": __builtins__,
            "__name__": "__main__",
        }

        if ctx.channel.id in self.sessions:
            await ctx.send(
                _("Already running a REPL session in this channel. Exit it with `quit`.")
            )
            return

        self.sessions.add(ctx.channel.id)
        await ctx.send(_("Enter code to execute or evaluate. `exit()` or `quit` to exit."))

        while True:

            def check_message(msg):
                return ctx.channel == msg.channel and ctx.author == msg.author

            response = await ctx.bot.wait_for("message", check=check_message)

            cleaned = self.cleanup_code(response.content)

            if cleaned in ("quit", "exit", "exit()"):
                await ctx.send(_("Exiting."))
                self.sessions.remove(ctx.channel.id)
                return

            executor = None
            if cleaned.count("\n") == 0:
                # single statement, potentially 'eval'
                try:
                    code = self.async_compile(cleaned, "<repl session>", "eval")
                except SyntaxError:
                    pass
                else:
                    executor = eval

            if executor is None:
                try:
                    code = self.async_compile(cleaned, "<repl session>", "exec")
                except SyntaxError as e:
                    await ctx.send(self.get_syntax_error(e))
                    continue

            variables["message"] = response

            stdout = io.StringIO()

            msg = ""

            try:
                with redirect_stdout(stdout):
                    if executor is None:
                        result = types.FunctionType(code, variables)()
                    else:
                        result = executor(code, variables)
                    result = await self.maybe_await(result)
            except:
                value = stdout.getvalue()
                msg = "{}{}".format(value, traceback.format_exc())
            else:
                value = stdout.getvalue()
                if result is not None:
                    msg = "{}{}".format(value, result)
                    variables["_"] = result
                elif value:
                    msg = "{}".format(value)

            msg = self.sanitize_output(ctx, msg)

            try:
                await self.send_interactive(ctx, self.get_pages(msg), box_lang="py")
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await ctx.send(_("Unexpected error: `{}`").format(e))

    @commands.command()
    @commands.is_owner()
    async def mock(self, ctx, user: discord.Member, *, command):
        """Mock another user invoking a command.

        The prefix must not be entered.
        """
        msg = copy(ctx.message)
        msg.author = user
        msg.content = ctx.prefix + command

        ctx.bot.dispatch("message", msg)

    @commands.command(name="mockmsg")
    @commands.is_owner()
    async def mock_msg(self, ctx, user: discord.Member, *, content: str):
        """Dispatch a message event as if it were sent by a different user.

        Only reads the raw content of the message. Attachments, embeds etc. are
        ignored.
        """
        old_author = ctx.author
        old_content = ctx.message.content
        ctx.message.author = user
        ctx.message.content = content

        ctx.bot.dispatch("message", ctx.message)

        # If we change the author and content back too quickly,
        # the bot won't process the mocked message in time.
        await asyncio.sleep(2)
        ctx.message.author = old_author
        ctx.message.content = old_content

def setup(bot):
    bot.add_cog(Dev())