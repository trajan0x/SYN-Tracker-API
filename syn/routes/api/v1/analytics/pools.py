#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
          Copyright Blaze 2021.
 Distributed under the Boost Software License, Version 1.0.
    (See accompanying file LICENSE_1_0.txt or copy at
          https://www.boost.org/LICENSE_1_0.txt)
"""

from collections import defaultdict
from typing import Any, Dict, List, Union
from datetime import datetime
from itertools import chain

from web3.exceptions import BadFunctionCallOutput
from flask import Blueprint, jsonify, request
from gevent.greenlet import Greenlet
from gevent.pool import Pool
import gevent

from syn.utils.data import SYN_DATA, cache, _forced_update, REDIS
from syn.utils.contract import get_virtual_price
from syn.utils.helpers import raise_if
from syn.utils import verify

pools_bp = Blueprint('pools_bp', __name__)

# 15m
TIMEOUT = 60 * 15
gpool = Pool()
metapools = list(SYN_DATA)
# No metapool on ETH.
metapools.remove('ethereum')

basepools = list(SYN_DATA)

pools = ['metapool', 'basepool']


def _dispatch(chain: str, block: Union[str, int]) -> List[Greenlet]:
    threads: List[Greenlet] = []

    if 'pool_contract' in SYN_DATA[chain]:
        threads.append(
            gpool.spawn(get_virtual_price, chain, block, 'pool_contract'))

    if 'ethpool_contract' in SYN_DATA[chain]:
        threads.append(
            gpool.spawn(get_virtual_price, chain, block, 'ethpool_contract'))

    return threads


def _convert_ret(ret: Dict[str, Any], res: Dict[str, float]) -> None:
    if 'ethpool_contract' in ret:
        res['neth'] = ret['ethpool_contract']
    elif 'pool_contract' in ret:
        res['nusd'] = ret['pool_contract']


@pools_bp.route('/price/virtual/', defaults={'chain': ''}, methods=['GET'])
@pools_bp.route('/price/virtual/<chain>', methods=['GET'])
@cache.cached(timeout=TIMEOUT, forced_update=_forced_update, query_string=True)
def price_virtual_chain(chain: str):
    if chain not in SYN_DATA:
        return (jsonify({
            'error': 'invalid chain',
            'valids': list(SYN_DATA),
        }), 400)

    block = request.args.get('block', 'latest')
    if block != 'latest':
        if not verify.isdigit(block):
            return (jsonify({'error': 'invalid block num'}), 400)

        block = int(block)

    threads: List[Greenlet] = _dispatch(chain, block)
    res: Dict[str, float] = {}
    gevent.joinall(threads)

    for thread in threads:
        _convert_ret(raise_if(thread.get(), None)[chain], res)

    try:
        return jsonify(res)
    except BadFunctionCallOutput:
        return (jsonify({'error': 'contract not deployed'}), 400)


@pools_bp.route('/price/virtual', methods=['GET'])
@cache.cached(timeout=TIMEOUT, forced_update=_forced_update)
def price_virtual():
    res: Dict[str, Dict[str, float]] = defaultdict(dict)
    jobs: Dict[str, List[Greenlet]] = {}

    for _chain in SYN_DATA:
        assert _chain not in jobs
        jobs[_chain] = _dispatch(_chain, 'latest')

    gevent.joinall(list(chain.from_iterable(jobs.values())))
    for k, v in jobs.items():
        for x in v:
            _convert_ret(raise_if(x.get(), None)[k], res[k])

    return jsonify(res)


@pools_bp.route('/price/virtual/<chain>/<date:date>', methods=['GET'])
@cache.cached(forced_update=_forced_update)
def price_virtual_chain_historical(chain: str, date: datetime):
    if chain not in SYN_DATA:
        return (jsonify({
            'error': 'invalid chain',
            'valids': list(SYN_DATA),
        }), 400)

    ret = verify.is_sane_date(date)
    if ret != True:
        return (jsonify({'error': ret, 'valids': []}), 400)

    _date = str(date.date())
    return jsonify({_date: REDIS.get(f'pools:{chain}:vp:{_date}')})
