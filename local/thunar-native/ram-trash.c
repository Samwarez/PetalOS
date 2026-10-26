/* PetalOS Private-to-RAM Trash dispatch. GPL-2.0-or-later. */
#include <gio/gio.h>
#include <stdlib.h>

gchar *
thunar_g_file_original_basename (GFile *file)
{
  if (g_file_has_uri_scheme (file, "trash"))
    {
      GFileInfo *info = g_file_query_info (file, G_FILE_ATTRIBUTE_TRASH_ORIG_PATH,
                                         G_FILE_QUERY_INFO_NONE, NULL, NULL);
      if (info != NULL)
        {
          const gchar *path = g_file_info_get_attribute_byte_string (info, G_FILE_ATTRIBUTE_TRASH_ORIG_PATH);
          gchar *name = path != NULL ? g_path_get_basename (path) : NULL;
          g_object_unref (info);
          if (name != NULL && *name != '\0' && !g_str_equal (name, ".")
              && !g_str_equal (name, "..") && !g_str_equal (name, "/"))
            return name;
          g_free (name);
        }
    }
  return g_file_get_basename (file);
}

gboolean
thunar_g_file_is_private (GFile *file)
{
  gchar *path = g_file_get_path (file);
  gchar *parent;
  char *canonical;
  gboolean result = FALSE;
  if (path == NULL)
    return FALSE;
  parent = g_path_get_dirname (path);
  canonical = realpath (parent, NULL);
  if (canonical != NULL)
    result = g_str_equal (canonical, "/mnt/private")
             || g_str_has_prefix (canonical, "/mnt/private/");
  free (canonical);
  g_free (parent);
  g_free (path);
  return result;
}

gboolean
thunar_g_file_trash_volatile (GFile *file, GCancellable *cancellable, GError **error)
{
  GSubprocess *child;
  gchar *path;
  gboolean result;
  if (!thunar_g_file_is_private (file))
    return g_file_trash (file, cancellable, error);
  if (g_cancellable_set_error_if_cancelled (cancellable, error))
    return FALSE;
  path = g_file_get_path (file);
  child = g_subprocess_new (G_SUBPROCESS_FLAGS_STDOUT_SILENCE | G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                           error, "/usr/local/bin/portable-trash", "--", path, NULL);
  g_free (path);
  if (child == NULL)
    return FALSE;
  result = g_subprocess_wait_check (child, cancellable, error);
  if (!result && cancellable != NULL && g_cancellable_is_cancelled (cancellable))
    {
      g_subprocess_force_exit (child);
      g_subprocess_wait (child, NULL, NULL);
    }
  else if (!result && g_subprocess_get_if_exited (child)
           && g_subprocess_get_exit_status (child) == 2)
    {
      g_clear_error (error);
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
                          "This item exceeds RAM Trash limits or free RAM is too low. The original was kept.");
    }
  if (!result)
    g_prefix_error (error, "RAM Trash failed; any complete RAM copy is retained. ");
  g_object_unref (child);
  return result;
}
