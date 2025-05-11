import 'dart:io';
import 'dart:convert';

Future<String> runPassportToExcel(String imgPath) async {
  final script = 'scripts/passport_to_excel.py';
  final outXlsx = 'passport.xlsx';
  final proc = await Process.start('python3', [script, imgPath, outXlsx]);

  await stdout.addStream(proc.stdout);
  await stderr.addStream(proc.stderr);

  final code = await proc.exitCode;
  if (code != 0) throw Exception('Скрипт завершился с кодом $code');
  return outXlsx;
}
