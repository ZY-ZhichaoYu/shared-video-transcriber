"""Optional real MCP protocol check. Usage: python tests/smoke_mcp.py <existing-job-id>."""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(command=sys.executable, args=[str(root / 'server.py')], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {'inspect_shared_video', 'get_video_job', 'cancel_video_job','inspect_local_video','get_video_handoff'} <= names
            result = await session.call_tool('get_video_job', {'job_id': sys.argv[1]})
            assert not result.isError, result
            text = '\n'.join(item.text for item in result.content if item.type == 'text')
            data = json.loads(text)
            assert data['status'] == 'done', data['status']
            assert data['segments']
            packet=await session.call_tool('get_video_handoff',{'job_id':sys.argv[1]})
            assert not packet.isError,packet
            print(json.dumps({'tools': len(names), 'status': data['status'], 'segments': len(data['segments']),
                              'frames': len(data['frames'])}))


if __name__ == '__main__':
    asyncio.run(main())
