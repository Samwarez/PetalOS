/* Isolated builder fixture only; GPL-2.0-or-later. */
#include <gio/gio.h>
#include <stdio.h>
#include <unistd.h>

gboolean thunar_g_file_trash_volatile (GFile *, GCancellable *, GError **);

int main (void)
{
  gchar *mapping = NULL, *scope = NULL;
  unsigned long inside, outside, count;
  if (getuid () != 1000
      || !g_file_get_contents ("/proc/self/uid_map", &mapping, NULL, NULL)
      || sscanf (mapping, "%lu %lu %lu", &inside, &outside, &count) != 3
      || inside != 1000 || count != 1
      || !g_file_get_contents ("/build/volatile-trash-fixture-only", &scope, NULL, NULL)
      || !g_str_equal (scope, "isolated disposable RAM builder\n"))
    return 2;
  g_free (mapping); g_free (scope);
  GFile *file = g_file_new_for_path ("/mnt/private/file");
  GError *error = NULL;
  gboolean ok = thunar_g_file_trash_volatile (file, NULL, &error);
  int result = !ok && error && g_error_matches (error, G_IO_ERROR, G_IO_ERROR_NO_SPACE) ? 0 : 1;
  g_clear_error (&error); g_object_unref (file);
  return result;
}
