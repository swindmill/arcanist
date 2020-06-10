from __future__ import absolute_import

import os
import json

from mercurial import (
  cmdutil,
  bookmarks,
  bundlerepo,
  error,
  hg,
  i18n,
  node,
  registrar,
)

_ = i18n._
cmdtable = {}
command = registrar.command(cmdtable)

@command(
  "arc-ls-markers",
  [('', 'output', '',
    _('file to output refs to'), _('FILE')),
  ] + cmdutil.remoteopts,
  _('[--output FILENAME] [SOURCE]'))
def lsmarkers(ui, repo, source=None, **opts):
  """list markers

  Show the current branch heads and bookmarks in the local working copy, or
  a specified path/URL.

  Markers are printed to stdout in JSON.

  (This is an Arcanist extension to Mercurial.)

  Returns 0 if listing the markers succeeds, 1 otherwise.
  """

  if source is None:
    markers = localmarkers(ui, repo)
  else:
    markers = remotemarkers(ui, repo, source, opts)

  json_opts = {
    'indent': 2,
    'sort_keys': True,
  }

  output_file = opts.get('output')
  if output_file:
    if os.path.exists(output_file):
      raise error.Abort(_('File "%s" already exists.' % output_file))
    with open(output_file, 'w+') as f:
      json.dump(markers, f, **json_opts)
  else:
    print json.dumps(markers, output_file, **json_opts)

  return 0

def localmarkers(ui, repo):
  markers = []

  active_node = repo['.'].node()
  all_heads = set(repo.heads())
  current_name = repo.dirstate.branch()
  saw_current = False
  saw_active = False

  branch_list = repo.branchmap().iterbranches()
  for branch_name, branch_heads, tip_node, is_closed in branch_list:
    for head_node in branch_heads:
      is_active = (head_node == active_node)
      is_tip = (head_node == tip_node)
      is_current = (branch_name == current_name)

      if is_current:
        saw_current = True

      if is_active:
        saw_active = True

      if is_closed:
        head_closed = True
      else:
        head_closed = bool(head_node not in all_heads)

      description = repo[head_node].description()

      markers.append({
        'type': 'branch',
        'name': branch_name,
        'node': node.hex(head_node),
        'isActive': is_active,
        'isClosed': head_closed,
        'isTip': is_tip,
        'isCurrent': is_current,
        'description': description,
      })

  # If the current branch (selected with "hg branch X") is not reflected in
  # the list of heads we selected, add a virtual head for it so callers get
  # a complete picture of repository marker state.

  if not saw_current:
    markers.append({
      'type': 'branch',
      'name': current_name,
      'node': None,
      'isActive': False,
      'isClosed': False,
      'isTip': False,
      'isCurrent': True,
      'description': None,
    })

  bookmarks = repo._bookmarks
  active_bookmark = repo._activebookmark

  for bookmark_name, bookmark_node in bookmarks.iteritems():
    is_active = (active_bookmark == bookmark_name)
    description = repo[bookmark_node].description()

    if is_active:
      saw_active = True

    markers.append({
      'type': 'bookmark',
      'name': bookmark_name,
      'node': node.hex(bookmark_node),
      'isActive': is_active,
      'description': description,
    })

  # If the current working copy state is not the head of a branch and there is
  # also no active bookmark, add a virtual marker for it so callers can figure
  # out exactly where we are.

  if not saw_active:
    markers.append({
      'type': 'commit',
      'name': None,
      'node': node.hex(active_node),
      'isActive': False,
      'isClosed': False,
      'isTip': False,
      'isCurrent': True,
      'description': repo['.'].description(),
    })

  return markers

def remotemarkers(ui, repo, source, opts):
  # Disable status output from fetching a remote.
  ui.quiet = True

  markers = []

  source, branches = hg.parseurl(ui.expandpath(source))
  remote = hg.peer(repo, opts, source)

  bundle, remotebranches, cleanup = bundlerepo.getremotechanges(
    ui,
    repo,
    remote)

  try:
    for n in remotebranches:
      ctx = bundle[n]
      markers.append({
        'type': 'branch',
        'name': ctx.branch(),
        'node': node.hex(ctx.node()),
      })
  finally:
    cleanup()

  with remote.commandexecutor() as e:
    remotemarks = bookmarks.unhexlifybookmarks(e.callcommand('listkeys', {
        'namespace': 'bookmarks',
    }).result())

  for mark in remotemarks:
    markers.append({
      'type': 'bookmark',
      'name': mark,
      'node': node.hex(remotemarks[mark]),
    })

  return markers