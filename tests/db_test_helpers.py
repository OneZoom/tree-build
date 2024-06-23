def delete_all_by_ott(db_context, table, ott):
    sql = f"DELETE FROM {table} WHERE ott={{0}};"
    db_context.execute(sql, ott)
    db_context.db_connection.commit()
