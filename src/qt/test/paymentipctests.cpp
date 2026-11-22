// Copyright (c) 2026 The Sugarchain developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://opensource.org/license/mit/.

#include <qt/test/paymentipctests.h>

#include <qt/paymentipc.h>

#include <QDataStream>
#include <QLocalServer>
#include <QLocalSocket>
#include <QLockFile>
#include <QTemporaryDir>
#include <QTest>
#include <QThread>

namespace {
void CheckDelivery(QLocalServer& server, const QStringList& names, const QString& request, int service_delay_ms = 0)
{
    // A Windows named pipe can wait for its reader before completing a write.
    QString error;
    PaymentIpcResult result{PaymentIpcResult::NO_SERVER};
    std::unique_ptr<QThread> sender{QThread::create([&] { result = SendPaymentIpc(names, {request}, error); })};
    sender->start();
    if (service_delay_ms) QTest::qSleep(service_delay_ms);
    std::unique_ptr<QLocalSocket> socket;
    if (server.hasPendingConnections() || server.waitForNewConnection(1000)) socket.reset(server.nextPendingConnection());
    QString received;
    if (socket && (socket->bytesAvailable() > 0 || socket->waitForReadyRead(1000))) {
        QDataStream in(socket.get());
        in.setVersion(QDataStream::Qt_4_0);
        in >> received;
    }
    sender->wait();
    QVERIFY2(error.isEmpty(), qPrintable(error));
    QCOMPARE(result, PaymentIpcResult::SENT);
    QCOMPARE(received, request);
}
} // namespace

void PaymentIpcTests::namesAreScoped()
{
    const QString main_name = PaymentIpcServerName("/example/main");
    QVERIFY(main_name.startsWith("SugarchainEn"));
    const QString old_name = PaymentIpcServerName("/example/main", true);
    QVERIFY(old_name.startsWith("SugarchainKomorebi"));
    QCOMPARE(main_name.mid(QString("SugarchainEn").size()), old_name.mid(QString("SugarchainKomorebi").size()));
    QVERIFY(main_name != PaymentIpcServerName("/example/main/regtest"));
    QVERIFY(main_name != PaymentIpcServerName("/different/main"));
}

void PaymentIpcTests::preferEnOnce_data()
{
    QTest::addColumn<int>("service_delay_ms");
    QTest::newRow("ready") << 0;
    QTest::newRow("busy") << 60;
}

void PaymentIpcTests::preferEnOnce()
{
    QFETCH(int, service_delay_ms);
    QTemporaryDir dir;
    const QString current_name = PaymentIpcServerName(dir.path());
    const QString old_name = PaymentIpcServerName(dir.path(), true);
    QLocalServer current, old;
    QVERIFY(current.listen(current_name));
    QVERIFY(old.listen(old_name));
    CheckDelivery(current, {current_name, old_name}, "sugarchain:test-only?label=En", service_delay_ms);
    QVERIFY(!current.waitForNewConnection(10));
    QVERIFY(!old.waitForNewConnection(10));
}

void PaymentIpcTests::legacyFallbackOnce()
{
    QTemporaryDir dir;
    const QString old_name = PaymentIpcServerName(dir.path(), true);
    QLocalServer old;
    QVERIFY(old.listen(old_name));
    CheckDelivery(old, {PaymentIpcServerName(dir.path()), old_name}, "sugarchain:test-only?label=Legacy");
    QVERIFY(!old.waitForNewConnection(10));
}

void PaymentIpcTests::noListener()
{
    QTemporaryDir dir;
    QString error;
    QCOMPARE(SendPaymentIpc({PaymentIpcServerName(dir.path()), PaymentIpcServerName(dir.path(), true)}, {"sugarchain:test-only"}, error), PaymentIpcResult::NO_SERVER);
    QVERIFY(error.isEmpty());
}

void PaymentIpcTests::concurrentStartupClaim()
{
    QTemporaryDir dir;
    const QString name = PaymentIpcServerName(dir.path());
    const QString lock_path = dir.filePath("startup.lock");
    QLocalServer first, second;
    std::unique_ptr<QLockFile> first_claim, second_claim;
    QString error;
    QVERIFY(ListenPaymentIpc(first, name, lock_path, first_claim, error));
    QVERIFY(!ListenPaymentIpc(second, name, lock_path, second_claim, error));
    QVERIFY(!error.isEmpty());
    QVERIFY(first.isListening());
    error.clear();
    CheckDelivery(first, {name}, "sugarchain:first-still-running");
    first.close();
    first_claim.reset();
    QVERIFY(ListenPaymentIpc(second, name, lock_path, second_claim, error));
}

void PaymentIpcTests::incompleteDeliveryDoesNotFallback()
{
    QTemporaryDir dir;
    const QString current_name = PaymentIpcServerName(dir.path());
    const QString old_name = PaymentIpcServerName(dir.path(), true);
    QLocalServer current, old;
    QVERIFY(current.listen(current_name));
    QVERIFY(old.listen(old_name));
    // Deliberately do not read from the receiving socket. Exceed its OS buffer
    // to force an uncertain partial write without crashing either process.
    QString error;
    const QString oversized = QStringLiteral("sugarchain:") + QString(4 * 1024 * 1024, QLatin1Char('x'));
    QCOMPARE(SendPaymentIpc({current_name, old_name}, {oversized}, error), PaymentIpcResult::FAILED);
    QVERIFY(!error.isEmpty());
    QVERIFY(!old.waitForNewConnection(10));
}
