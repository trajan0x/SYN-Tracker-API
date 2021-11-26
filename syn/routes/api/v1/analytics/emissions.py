#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
		  Copyright Blaze 2021.
 Distributed under the Boost Software License, Version 1.0.
	(See accompanying file LICENSE_1_0.txt or copy at
		  https://www.boost.org/LICENSE_1_0.txt)
"""

from decimal import Decimal
from typing import Dict, List

from web3.exceptions import BadFunctionCallOutput
from flask import Blueprint, jsonify, request
from gevent import Greenlet
import gevent

from syn.utils.contract import get_synapse_emissions
from syn.utils.data import SYN_DATA
from syn.utils import verify

emissions_bp = Blueprint('emissions_bp', __name__)


@emissions_bp.route('/weekly/', defaults={'chain': ''}, methods=['GET'])
@emissions_bp.route('/weekly/<chain>', methods=['GET'])
def weekly_emissions_chain(chain: str):
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

    try:
        return jsonify({
            'emission':
            get_synapse_emissions(
                chain,
                block,
                multiplier=60 * 60 * 24 * 7,
            )
        })
    except BadFunctionCallOutput:
        return (jsonify({'error': 'contract not deployed'}), 400)


@emissions_bp.route('/weekly', methods=['GET'])
def weekly_emissions():
    res: Dict[str, Decimal] = {}
    jobs: List[Greenlet] = []

    def dispatch(chain: str):
        ret = get_synapse_emissions(chain, multiplier=60 * 60 * 24 * 7)
        res.update({chain: ret})

    for chain in SYN_DATA:
        jobs.append(gevent.spawn(dispatch, chain))

    gevent.joinall(jobs)
    return jsonify(res)
