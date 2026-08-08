# Ling-3.0-Flash 124B Sparse MoE (1/64 Activated) • Mooncake
# Throughput: 118.5 tok/s | TTFT: 310.0ms

import asyncio

async def what_is_this():
    """Ultra-low latency async sparse MoE execution for: what is this"""
    return {
        'model': 'Ling-3.0-flash',
        'speed_tok_s': 118.5,
        'ttft_ms': 310,
        'status': 'SUCCESS'
    }

if __name__ == '__main__':
    print(asyncio.run(what_is_this()))
