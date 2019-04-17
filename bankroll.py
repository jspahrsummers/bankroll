from argparse import ArgumentParser, Namespace
from functools import reduce
from ib_insync import IB
from itertools import groupby
from model import Instrument, Stock, Position, Trade
from pathlib import Path
from typing import Iterable, List

import analysis
import ibkr
import fidelity
import schwab
import vanguard

parser = ArgumentParser()

parser.add_argument(
    '--lenient',
    help=
    'Attempt to ignore invalid data instead of erroring out. May not be supported for all data sources.',
    default=False,
    action='store_true')
parser.add_argument('--no-lenient', dest='lenient', action='store_false')

ibGroup = parser.add_argument_group(
    'IB', 'Options for importing data from Interactive Brokers.')
ibGroup.add_argument(
    '--twsport',
    help=
    'Local port to connect to Trader Workstation, to import live portfolio data',
    type=int)
ibGroup.add_argument(
    '--flextoken',
    help=
    'Token ID from IB\'s Flex Web Service: https://www.interactivebrokers.com/en/software/am/am/reports/flex_web_service_version_3.htm'
)
ibGroup.add_argument(
    '--flexquery',
    help=
    'Query ID from IB\'s Flex Web Service: https://www.interactivebrokers.com/en/software/am/am/reports/flex_web_service_version_3.htm',
    type=int)
ibGroup.add_argument(
    '--ibtrades',
    help=
    'Path to exported XML of trade confirmations from IB\'s Flex Web Service',
    type=Path)

fidelityGroup = parser.add_argument_group(
    'Fidelity',
    'Options for importing data from local files in Fidelity\'s CSV export format.'
)
fidelityGroup.add_argument('--fidelitypositions',
                           help='Path to exported CSV of Fidelity positions',
                           type=Path)
fidelityGroup.add_argument(
    '--fidelitytransactions',
    help='Path to exported CSV of Fidelity transactions',
    type=Path)

schwabGroup = parser.add_argument_group(
    'Schwab',
    'Options for importing data from local files in Charles Schwab\'s CSV export format.'
)
schwabGroup.add_argument('--schwabpositions',
                         help='Path to exported CSV of Schwab positions',
                         type=Path)
schwabGroup.add_argument('--schwabtransactions',
                         help='Path to exported CSV of Schwab transactions',
                         type=Path)

vanguardGroup = parser.add_argument_group(
    'Vanguard',
    'Options for importing data from local files in Vanguard\'s CSV export format.'
)
vanguardGroup.add_argument(
    '--vanguardstatement',
    help='Path to exported CSV of Vanguard positions and trades',
    type=Path)


def combinePositions(positions: Iterable[Position]) -> Iterable[Position]:
    return (reduce(lambda a, b: a.combine(b), ps)
            for i, ps in groupby(sorted(positions, key=lambda p: p.instrument),
                                 key=lambda p: p.instrument))


positions: List[Position] = []
trades: List[Trade] = []


def printPositions(args: Namespace) -> None:
    for p in sorted(positions, key=lambda p: p.instrument):
        print(p)

        if not isinstance(p.instrument, Stock):
            continue

        print('\tCost basis: {}'.format(p.costBasis))

        if args.realized_basis:
            realizedBasis = analysis.realizedBasisForSymbol(
                p.instrument.symbol, trades=trades)
            print('\tRealized basis: {}'.format(realizedBasis))


def printTrades(args: Namespace) -> None:
    for t in sorted(trades, key=lambda t: t.date, reverse=True):
        print(t)


commands = {
    'positions': printPositions,
    'trades': printTrades,
}

subparsers = parser.add_subparsers(dest='command', help='What to inspect')

positionsParser = subparsers.add_parser(
    'positions',
    help='Operations upon the imported list of portfolio positions')
positionsParser.add_argument(
    '--realized-basis',
    help='Calculate realized basis for stock positions',
    default=False,
    action='store_true')

tradesParser = subparsers.add_parser(
    'trades', help='Operations upon the imported list of trades')

if __name__ == '__main__':
    args = parser.parse_args()
    if not args.command:
        parser.print_usage()
        quit(1)

    if args.fidelitypositions:
        positions += fidelity.parsePositions(args.fidelitypositions,
                                             lenient=args.lenient)

    if args.fidelitytransactions:
        trades += fidelity.parseTransactions(args.fidelitytransactions,
                                             lenient=args.lenient)

    if args.schwabpositions:
        positions += schwab.parsePositions(args.schwabpositions,
                                           lenient=args.lenient)

    if args.schwabtransactions:
        trades += schwab.parseTransactions(args.schwabtransactions,
                                           lenient=args.lenient)

    if args.vanguardstatement:
        positionsAndTrades = vanguard.parsePositionsAndTrades(
            args.vanguardstatement, lenient=args.lenient)
        positions += positionsAndTrades.positions
        trades += positionsAndTrades.trades

    if args.twsport:
        ib = IB()
        ib.connect('127.0.0.1', port=args.twsport)
        positions += ibkr.downloadPositions(ib, lenient=args.lenient)

    if args.flextoken or args.flexquery:
        if not args.flextoken or not args.flexquery:
            raise Exception(
                'Both a Flex token and a Flex query ID are required to download trade reports'
            )

        trades += ibkr.downloadTrades(token=args.flextoken,
                                      queryID=args.flexquery,
                                      lenient=args.lenient)

    if args.ibtrades:
        trades += ibkr.parseTrades(args.ibtrades, lenient=args.lenient)

    positions = list(combinePositions(positions))
    commands[args.command](args)