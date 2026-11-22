// Copyright (c) 2026 The Sugarchain developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://opensource.org/license/mit/.

#ifndef BITCOIN_QT_TEST_PAYMENTIPCTESTS_H
#define BITCOIN_QT_TEST_PAYMENTIPCTESTS_H

#include <QObject>

class PaymentIpcTests : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void namesAreScoped();
    void preferEnOnce_data();
    void preferEnOnce();
    void legacyFallbackOnce();
    void noListener();
    void concurrentStartupClaim();
    void incompleteDeliveryDoesNotFallback();
};

#endif // BITCOIN_QT_TEST_PAYMENTIPCTESTS_H
