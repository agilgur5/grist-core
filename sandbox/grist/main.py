"""
This module defines what sandbox functions are made available to the Node controller,
and starts the grist sandbox. See engine.py for the API documentation.
"""
import sys
sys.path.append('thirdparty')
# pylint: disable=wrong-import-position

import marshal
import functools

import six

import actions
import engine
import migrations
import schema
import useractions
import objtypes
from acl_formula import parse_acl_formula
from sandbox import get_default_sandbox
from imports.register import register_import_parsers

import logger
log = logger.Logger(__name__, logger.INFO)

def table_data_from_db(table_name, table_data_repr):
  if table_data_repr is None:
    return actions.TableData(table_name, [], {})
  table_data_parsed = marshal.loads(table_data_repr)
  table_data_parsed = {key.decode("utf8"): value for key, value in table_data_parsed.items()}
  id_col = table_data_parsed.pop("id")
  return actions.TableData(table_name, id_col,
                           actions.decode_bulk_values(table_data_parsed, _decode_db_value))

def _decode_db_value(value):
  # Decode database values received from SQLite's allMarshal() call. These are encoded by
  # marshalling certain types and storing as BLOBs (received in Python as binary strings, as
  # opposed to text which is received as unicode). See also encodeValue() in DocStorage.js
  t = type(value)
  if t == six.binary_type:
    return objtypes.decode_object(marshal.loads(value))
  else:
    return value

def run(sandbox):
  eng = engine.Engine()

  def export(method):
    # Wrap each method so that it logs a message that it's being called.
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
      log.debug("calling %s" % method.__name__)
      return method(*args, **kwargs)

    sandbox.register(method.__name__, wrapper)

  @export
  def apply_user_actions(action_reprs, user=None):
    action_group = eng.apply_user_actions([useractions.from_repr(u) for u in action_reprs], user)
    return eng.acl_split(action_group).to_json_obj()

  @export
  def fetch_table(table_id, formulas=True, query=None):
    return actions.get_action_repr(eng.fetch_table(table_id, formulas=formulas, query=query))

  @export
  def fetch_table_schema():
    return eng.fetch_table_schema()

  @export
  def autocomplete(txt, table_id, column_id, user):
    return eng.autocomplete(txt, table_id, column_id, user)

  @export
  def find_col_from_values(values, n, opt_table_id):
    return eng.find_col_from_values(values, n, opt_table_id)

  @export
  def fetch_meta_tables(formulas=True):
    return {table_id: actions.get_action_repr(table_data)
            for (table_id, table_data) in six.iteritems(eng.fetch_meta_tables(formulas))}

  @export
  def load_meta_tables(meta_tables, meta_columns):
    return eng.load_meta_tables(table_data_from_db("_grist_Tables", meta_tables),
                                table_data_from_db("_grist_Tables_column", meta_columns))

  @export
  def load_table(table_name, table_data):
    return eng.load_table(table_data_from_db(table_name, table_data))

  @export
  def create_migrations(all_tables, metadata_only=False):
    doc_actions = migrations.create_migrations(
      {t: table_data_from_db(t, data) for t, data in six.iteritems(all_tables)}, metadata_only)
    return [actions.get_action_repr(action) for action in doc_actions]

  @export
  def get_version():
    return schema.SCHEMA_VERSION

  @export
  def get_formula_error(table_id, col_id, row_id):
    return objtypes.encode_object(eng.get_formula_error(table_id, col_id, row_id))

  export(parse_acl_formula)
  export(eng.load_empty)
  export(eng.load_done)

  register_import_parsers(sandbox)

  sandbox.run()

def main():
  run(get_default_sandbox())

if __name__ == "__main__":
  main()
