# -*- coding: utf-8 -*-
"""Student-owned MCP server. Never start a server on module import."""
from practice_common.runtime import todo


def main():
    # TODO(P2-MCP-SERVER): choose and pin an MCP SDK, use stdio transport.
    # Register search_notes/read_note tools, course_catalog resource,
    # and compare_papers prompt. Reuse chapter 1 implementations.
    # stdout belongs to the protocol; send diagnostic logs to stderr.
    todo("P2-MCP-SERVER", "注册两个查询工具、课程 resource 和比较 prompt，启动 stdio server")


if __name__ == "__main__":
    main()
