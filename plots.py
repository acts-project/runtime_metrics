#!/usr/bin/env python3
from datetime import datetime
import typer
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from lxml import etree, objectify
import re
from github import Github, Auth

commit_message_cache = {}


def process_links(fname: Path, gh: Github):
    with fname.open("rb") as fh:
        tree = etree.parse(fh)

    root = tree.getroot()

    axis = root.find(".//{http://www.w3.org/2000/svg}g[@id='matplotlib.axis_1']")

    repo = gh.get_repo("acts-project/acts")

    for tick in axis:
        if not tick.get("id").startswith("xtick_"):
            continue

        text = None
        for child in tick:
            if child.get("id").startswith("text_"):
                text = child
                break

        assert text is not None, "Unable to find text element"

        commit = None
        for child in text:
            if not isinstance(child, etree._Comment):
                continue
            if re.match(r"[a-f0-9]{7}", child.text.strip()):
                commit = child.text.strip()
                break

        assert commit is not None, "Unable to find commit hash"

        if commit not in commit_message_cache:
            commit_obj = repo.get_commit(commit)
            commit_message_cache[commit] = commit_obj.commit.message

        commit_message = commit_message_cache[commit]

        href = f"https://github.com/acts-project/acts/commit/{commit}"

        link = etree.Element("a", attrib={"href": href})
        tick.addprevious(link)
        link.insert(0, tick)

        title = etree.Element("title")
        title.text = commit_message
        link.append(title)

    fname.write_text(etree.tostring(root, pretty_print=True).decode())


def main(
    data: Path = typer.Argument(..., exists=True),
    outdir: Path = Path.cwd(),
    gh_token: str = typer.Option(..., envvar="GH_TOKEN"),
):
    gh = Github(auth=Auth.Token(gh_token))

    df = pd.read_csv(data)
    df.date = pd.to_datetime(df.date, format="%Y-%m-%dT%H-%M-%S")

    outdir.mkdir(parents=True, exist_ok=True)

    plots = []

    for g, d in df.groupby("label"):
        d = d.tail(15)

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(np.arange(len(d)), d.rss / 1e6, label="RSS")
        ax.plot(np.arange(len(d)), d.vms / 1e6, label="VMS")

        ax.set(xlabel="Time", ylabel="Memory [MB]", title=g)
        ax.set_xticks(np.arange(len(d)))
        ticklabels = [
            f"{date}\n{commit[:7]}" for date, commit in zip(d.date, d.commit_sha)
        ]
        ax.set_xticklabels(ticklabels, rotation=45, ha="right")
        ax.legend()
        plt.setp(ax.get_xticklabels(), backgroundcolor="white")
        fig.tight_layout()
        fname = outdir / f"{g}_memory.svg"
        fig.savefig(fname)

        process_links(fname, gh=gh)

        plots.append(fname)

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(np.arange(len(d)), d.time, label="time")

        ax.set(xlabel="Time", ylabel="Wall time [s]", title=g)
        ax.set_xticks(np.arange(len(d)))
        ticklabels = [
            f"{date}\n{commit[:7]}" for date, commit in zip(d.date, d.commit_sha)
        ]
        ax.set_xticklabels(ticklabels, rotation=45, ha="right")
        ax.legend()
        plt.setp(ax.get_xticklabels(), backgroundcolor="white")
        fig.tight_layout()
        fname = outdir / f"{g}_walltime.svg"
        fig.savefig(fname)

        process_links(fname, gh=gh)
        plots.append(fname)

    content = ""

    for plot in plots:
        content += f"<div>{plot.read_text()}</div>"

    index_file = outdir / "index.html"
    index_file.write_text(
        """<!DOCTYPE html>
<html>
<head>
    <title>Runtime metrics</title>
    <style>
    .wrapper {{
        max-width: 1500px;
        margin: 0 auto;
    }}
    .grid {{
        display: grid;
        grid-template-columns: repeat(2, 50%);
    }}
    .grid svg {{
        width:100%;
        height:auto;
    }}
    </style>
</head>
<body>
<div class="wrapper">
    <h1>Runtime metrics</h1>
    Generated: {date}<br>
    <div class="grid">
    {content}
    </div>
</div>
</body>
</html>
    """.format(
            content=content, date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )


typer.run(main)
