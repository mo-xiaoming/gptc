#!/usr/bin/env python3

import time
from openai.types.beta.threads.message_content_text import Text, TextAnnotation
from openai.types.file_object import FileObject
from rich.console import Console
from rich.markdown import Markdown
from dataclasses import dataclass
from typing import List, Final
from openai import OpenAI, OpenAIError
from openai.types.beta.assistant import Assistant
from openai.types.beta.thread import Thread
from openai.types.beta.threads import ThreadMessage, Run
import argparse


@dataclass
class Args:
    """Command line arguments."""

    model: str = "gpt-3.5-turbo-1106"
    instructions: str | None = None

    @staticmethod
    def from_command_line() -> "Args":
        """Parse command line arguments."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--model",
            type=str,
            default=Args.model,
            help=f"Model to use for OpenAI, default is `{Args.model}`",
        )
        parser.add_argument(
            "--instructions",
            type=str,
            help="Instructions for OpenAI",
        )
        args = parser.parse_args()
        return Args(model=args.model)


def _read_system_prompt() -> str:
    try:
        with open("system_prompt.txt", "r") as f:
            return f.read()
    except FileNotFoundError:
        print("File 'system_prompt.txt' not found. Using default prompt.")
        return "You are a helpful assistant."


def _get_user_question() -> str:
    # 3 enters to end input
    END: Final = 2
    enter_num: int = END
    waiting_to_end: bool = False

    multiline_input: List[str] = []
    print(f"Enter text, type Enter {END} times to end input.")

    while True:
        line: str = input()
        if line == "":
            if not waiting_to_end:
                waiting_to_end = True
            enter_num -= 1
        else:
            waiting_to_end = False
            enter_num = END
        if waiting_to_end and enter_num == 0:
            break
        multiline_input.append(line)

    return "\n".join(multiline_input)


if __name__ == "__main__":
    args: Args = Args.from_command_line()
    client: OpenAI = OpenAI()
    console = Console()

    try:
        assistant: Assistant = client.beta.assistants.create(
            name="Code Lingo Assistant",
            instructions=_read_system_prompt()
            if args.instructions is None
            else args.instructions,
            # tools=[{"type": "code_interpreter"}, {"type": "retrieval"}],
            model=args.model,
        )
        thread: Thread = client.beta.threads.create()

        while True:
            try:
                question: str = _get_user_question()
            except EOFError:
                break
            message: ThreadMessage = client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=question,
            )
            run: Run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id,
            )
            while run.status in ["queued", "in_progress"]:
                time.sleep(1)
                run: Run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id,
                )
                if run.status != "completed":
                    print(".", end="", flush=True)
            if run.status != "completed":
                continue
            if run.status == "failed":
                print(f"failed: {run.last_error}")
                continue
            messages = client.beta.threads.messages.list(
                thread_id=thread.id,
            )
            for message in messages:
                message: ThreadMessage = client.beta.threads.messages.retrieve(
                    thread_id=thread.id,
                    message_id=message.id,
                )
                if message.content[0].type == "text":
                    message_content: Text = message.content[0].text
                    annotations: List[TextAnnotation] = message_content.annotations
                    citations: List[str] = []
                    for index, annotation in enumerate(annotations):
                        message_content.value = message_content.value.replace(
                            annotation.text,
                            f"[{index}]",
                        )
                        if file_citation := getattr(annotation, "file_citation", None):
                            cited_file: FileObject = client.files.retrieve(
                                file_citation.file_id
                            )
                            citations.append(
                                f"[{index}] {file_citation.quote} from {cited_file.filename}"
                            )
                        elif file_path := getattr(annotation, "file_path", None):
                            cited_file: FileObject = client.files.retrieve(
                                file_path.file_id
                            )
                            citations.append(
                                f"[{index}] Click <here> to download {cited_file.filename}"
                            )
                    message_content.value += "\n" + "\n".join(citations)
                    md: Markdown = Markdown(message_content.value)
                    console.print(md)
                elif message.content[0].type == "image_file":
                    console.print(message.content[0].image_file.file_id)
                break
            console.rule()
    except OpenAIError as e:
        print(e)
